##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2018, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

import json
import logging
from abc import ABCMeta, abstractmethod, abstractproperty
import six
from socket import error as SOCKETErrorException
from smtplib import SMTPConnectError, SMTPResponseException,\
    SMTPServerDisconnected, SMTPDataError,SMTPHeloError, SMTPException, \
    SMTPAuthenticationError, SMTPSenderRefused, SMTPRecipientsRefused
from flask import current_app, render_template, url_for, make_response, flash,\
    Response, request, after_this_request, redirect
from flask_babel import gettext
from flask_login import current_user, login_required
from flask_security.decorators import anonymous_user_required
from flask_gravatar import Gravatar
from pgadmin.settings import get_setting
from pgadmin.utils import PgAdminModule
from pgadmin.utils.ajax import make_json_response
from pgadmin.utils.preferences import Preferences
from werkzeug.datastructures import MultiDict
from flask_security.views import _security, _commit, _render_json, _ctx
from flask_security.changeable import change_user_password
from flask_security.recoverable import reset_password_token_status, \
    generate_reset_password_token, update_password
from flask_security.utils import config_value, do_flash, get_url, get_message,\
    slash_url_suffix, login_user, send_mail
from flask_security.signals import reset_password_instructions_sent


import config
from pgadmin import current_blueprint

try:
    import urllib.request as urlreq
except:
    import urllib2 as urlreq

MODULE_NAME = 'browser'


class BrowserModule(PgAdminModule):
    LABEL = gettext('Browser')

    def get_own_stylesheets(self):
        stylesheets = []
        # Add browser stylesheets
        for (endpoint, filename) in [
            ('static', 'vendor/codemirror/codemirror.css'),
            ('static', 'vendor/codemirror/addon/dialog/dialog.css'),
            ('static', 'vendor/jQuery-contextMenu/jquery.contextMenu.css' if current_app.debug
            else 'vendor/jQuery-contextMenu/jquery.contextMenu.min.css'),
            ('static', 'vendor/wcDocker/wcDocker.css' if current_app.debug
            else 'vendor/wcDocker/wcDocker.min.css'),
            ('browser.static', 'css/browser.css'),
            ('browser.static', 'vendor/aciTree/css/aciTree.css')
        ]:
            stylesheets.append(url_for(endpoint, filename=filename))
        stylesheets.append(url_for('browser.browser_css'))
        return stylesheets

    def get_own_javascripts(self):
        scripts = list()
        scripts.append({
            'name': 'alertify',
            'path': url_for(
                'static',
                filename='vendor/alertifyjs/alertify' if current_app.debug
                else 'vendor/alertifyjs/alertify.min'
            ),
            'exports': 'alertify',
            'preloaded': True
        })
        scripts.append({
            'name': 'jqueryui.position',
            'path': url_for(
                'static',
                filename='vendor/jQuery-contextMenu/jquery.ui.position' if \
                    current_app.debug else \
                    'vendor/jQuery-contextMenu/jquery.ui.position.min'
            ),
            'deps': ['jquery'],
            'exports': 'jQuery.ui.position',
            'preloaded': True
        })
        scripts.append({
            'name': 'jquery.contextmenu',
            'path': url_for(
                'static',
                filename='vendor/jQuery-contextMenu/jquery.contextMenu' if \
                    current_app.debug else \
                    'vendor/jQuery-contextMenu/jquery.contextMenu.min'
            ),
            'deps': ['jquery', 'jqueryui.position'],
            'exports': 'jQuery.contextMenu',
            'preloaded': True
        })
        scripts.append({
            'name': 'jquery.aciplugin',
            'path': url_for(
                'browser.static',
                filename='vendor/aciTree/jquery.aciPlugin.min'
            ),
            'deps': ['jquery'],
            'exports': 'aciPluginClass',
            'preloaded': True
        })
        scripts.append({
            'name': 'jquery.acitree',
            'path': url_for(
                'browser.static',
                filename='vendor/aciTree/jquery.aciTree' if
                current_app.debug else 'vendor/aciTree/jquery.aciTree.min'
            ),
            'deps': ['jquery', 'jquery.aciplugin'],
            'exports': 'aciPluginClass.plugins.aciTree',
            'preloaded': True
        })
        scripts.append({
            'name': 'jquery.acisortable',
            'path': url_for(
                'browser.static',
                filename='vendor/aciTree/jquery.aciSortable.min'
            ),
            'deps': ['jquery', 'jquery.aciplugin'],
            'exports': 'aciPluginClass.plugins.aciSortable',
            'when': None,
            'preloaded': True
        })
        scripts.append({
            'name': 'jquery.acifragment',
            'path': url_for(
                'browser.static',
                filename='vendor/aciTree/jquery.aciFragment.min'
            ),
            'deps': ['jquery', 'jquery.aciplugin'],
            'exports': 'aciPluginClass.plugins.aciFragment',
            'when': None,
            'preloaded': True
        })
        scripts.append({
            'name': 'wcdocker',
            'path': url_for(
                'static',
                filename='vendor/wcDocker/wcDocker' if current_app.debug
                else 'vendor/wcDocker/wcDocker.min'
            ),
            'deps': ['jquery.contextmenu'],
            'exports': '',
            'preloaded': True
        })

        scripts.append({
            'name': 'pgadmin.browser.datamodel',
            'path': url_for('browser.static', filename='js/datamodel'),
            'preloaded': True
        })

        for name, script in [
            ['pgadmin.browser', 'js/browser'],
            ['pgadmin.browser.endpoints', 'js/endpoints'],
            ['pgadmin.browser.error', 'js/error']]:
            scripts.append({
                'name': name,
                'path': url_for('browser.index') + script,
                'preloaded': True
            })

        for name, script in [
            ['pgadmin.browser.node', 'js/node'],
            ['pgadmin.browser.messages', 'js/messages'],
            ['pgadmin.browser.collection', 'js/collection']]:
            scripts.append({
                'name': name,
                'path': url_for('browser.index') + script,
                'preloaded': True,
                'deps': ['pgadmin.browser.datamodel']
            })

        for name, end in [
            ['pgadmin.browser.menu', 'js/menu'],
            ['pgadmin.browser.panel', 'js/panel'],
            ['pgadmin.browser.frame', 'js/frame']]:
            scripts.append({
                'name': name, 'path': url_for('browser.static', filename=end),
                'preloaded': True})

        scripts.append({
            'name': 'pgadmin.browser.node.ui',
            'path': url_for('browser.static', filename='js/node.ui'),
            'when': 'server_group'
        })

        for module in self.submodules:
            scripts.extend(module.get_own_javascripts())
        return scripts

    def register_preferences(self):
        self.show_system_objects = self.preference.register(
            'display', 'show_system_objects',
            gettext("Show system objects?"), 'boolean', False,
            category_label=gettext('Display')
        )
        self.table_row_count_threshold = self.preference.register(
            'properties', 'table_row_count_threshold',
            gettext("Count rows if estimated less than"), 'integer', 2000,
            category_label=gettext('Properties')
        )

    def get_exposed_url_endpoints(self):
        """
        Returns:
            list: a list of url endpoints exposed to the client.
        """
        return ['browser.index', 'browser.nodes']

blueprint = BrowserModule(MODULE_NAME, __name__)


@six.add_metaclass(ABCMeta)
class BrowserPluginModule(PgAdminModule):
    """
    Abstract base class for browser submodules.

    It helps to define the node for each and every node comes under the browser
    tree. It makes sure every module comes under browser will have prefix
    '/browser', and sets the 'url_prefix', 'static_url_path', etc.

    Also, creates some of the preferences to be used by the node.
    """

    browser_url_prefix = blueprint.url_prefix + '/'
    SHOW_ON_BROWSER = True

    def __init__(self, import_name, **kwargs):
        """
        Construct a new 'BrowserPluginModule' object.

        :param import_name: Name of the module
        :param **kwargs:    Extra parameters passed to the base class
                            pgAdminModule.

        :return: returns nothing

        It sets the url_prefix to based on the 'node_path'. And,
        static_url_path to relative path to '/static'.

        Every module extended from this will be identified as 'NODE-<type>'.

        Also, create a preference 'show_node_<type>' to fetch whether it
        can be shown in the browser or not. Also,  refer to the browser-preference.
        """
        kwargs.setdefault("url_prefix", self.node_path)
        kwargs.setdefault("static_url_path", '/static')

        self.browser_preference = None
        self.pref_show_system_objects = None
        self.pref_show_node = None

        super(BrowserPluginModule, self).__init__(
            "NODE-%s" % self.node_type,
            import_name,
            **kwargs
        )

    @property
    def jssnippets(self):
        """
        Returns a snippet of javascript to include in the page
        """
        return []

    @property
    def module_use_template_javascript(self):
        """
        Returns whether Jinja2 template is used for generating the javascript
        module.
        """
        return False

    def get_own_javascripts(self):
        """
        Returns the list of javascripts information used by the module.

        Each javascripts information must contain name, path of the script.

        The name must be unique for each module, hence - in order to refer them
        properly, we do use 'pgadmin.node.<type>' as norm.

        That can also refer to when to load the script.

        i.e.
        We may not need to load the javascript of table node, when we're
        not yet connected to a server, and no database is loaded. Hence - it
        make sense to load them when a database is loaded.

        We may also add 'deps', which also refers to the list of javascripts,
        it may depends on.
        """
        scripts = []

        if self.module_use_template_javascript:
            scripts.extend([{
                'name': 'pgadmin.node.%s' % self.node_type,
                'path': url_for('browser.index') + '%s/module' % self.node_type,
                'when': self.script_load,
                'is_template': True
            }])
        else:
            scripts.extend([{
                'name': 'pgadmin.node.%s' % self.node_type,
                'path': url_for(
                    '%s.static'% self.name, filename=('js/%s' % self.node_type)
                ),
                'when': self.script_load,
                'is_template': False
            }])

        for module in self.submodules:
            scripts.extend(module.get_own_javascripts())

        return scripts

    def generate_browser_node(
            self, node_id, parent_id, label, icon, inode, node_type, **kwargs
    ):
        """
        Helper function to create a browser node for this particular subnode.

        :param node_id:   Unique Id for each node
        :param parent_id: Id of the parent.
        :param label:     Label for the node
        :param icon:      Icon for displaying along with this node on browser
                          tree. Icon refers to a class name, it refers to.
        :param inode:     True/False.
                          Used by the browser tree node to check, if the
                          current node will have children or not.
        :param node_type: String to refer to the node type.
        :param **kwargs:  A node can have extra information other than this
                          data, which can be passed as key-value pair as
                          argument here.
                          i.e. A database, server node can have extra
                          information like connected, or not.

        Returns a dictionary object representing this node object for the
        browser tree.
        """
        obj = {
            "id": "%s/%s" % (node_type, node_id),
            "label": label,
            "icon": icon,
            "inode": inode,
            "_type": node_type,
            "_id": node_id,
            "_pid": parent_id,
            "module": 'pgadmin.node.%s' % node_type
        }
        for key in kwargs:
            obj.setdefault(key, kwargs[key])
        return obj

    @property
    def csssnippets(self):
        """
        Returns a snippet of css to include in the page
        """
        snippets = [
            render_template(
                "browser/css/node.css",
                node_type=self.node_type,
                _=gettext
            )]

        for submodule in self.submodules:
            snippets.extend(submodule.csssnippets)
        return snippets

    @abstractmethod
    def get_nodes(self):
        """
        Each browser module is responsible for fetching
        its own tree subnodes.
        """
        return []

    @abstractproperty
    def node_type(self):
        pass

    @abstractproperty
    def script_load(self):
        """
        This property defines, when to load this script.
        In order to allow creation of an object, we need to load script for any
        node at the parent level.

        i.e.
        - In order to allow creating a server object, it should be loaded at
          server-group node.
        """
        pass

    @property
    def node_path(self):
        """
        Defines the url path prefix for this submodule.
        """
        return self.browser_url_prefix + self.node_type

    @property
    def javascripts(self):
        """
        Override the javascript of PgAdminModule, so that - we don't return
        javascripts from the get_own_javascripts itself.
        """
        return []

    @property
    def label(self):
        """
        Module label.
        """
        return self.LABEL

    @property
    def show_node(self):
        """
        A proper to check to show node for this module on the browser tree or not.

        Relies on show_node preference object, otherwise on the SHOW_ON_BROWSER
        default value.
        """
        if self.pref_show_node:
            return self.pref_show_node.get()
        else:
            return self.SHOW_ON_BROWSER

    @property
    def show_system_objects(self):
        """
        Show/Hide the system objects in the database server.
        """
        if self.pref_show_system_objects:
            return self.pref_show_system_objects.get()
        else:
            return False

    def register_preferences(self):
        """
        Registers the preferences object for this module.

        Sets the browser_preference, show_system_objects, show_node preference
        objects for this submodule.
        """
        # Add the node informaton for browser, not in respective node preferences
        self.browser_preference = blueprint.preference
        self.pref_show_system_objects = blueprint.preference.preference(
            'display', 'show_system_objects'
        )
        self.pref_show_node = self.browser_preference.preference(
            'node', 'show_node_' + self.node_type,
            self.label, 'boolean', self.SHOW_ON_BROWSER, category_label=gettext('Nodes')
        )


@blueprint.route("/")
@login_required
def index():
    """Render and process the main browser window."""
    # Get the Gravatar
    Gravatar(
        current_app,
        size=100,
        rating='g',
        default='retro',
        force_default=False,
        use_ssl=True,
        base_url=None
    )

    msg = None
    # Get the current version info from the website, and flash a message if
    # the user is out of date, and the check is enabled.
    if config.UPGRADE_CHECK_ENABLED:
        data = None
        url = '%s?version=%s' % (config.UPGRADE_CHECK_URL, config.APP_VERSION)
        current_app.logger.debug('Checking version data at: %s' % url)

        try:
            # Do not wait for more than 5 seconds.
            # It stuck on rendering the browser.html, while working in the
            # broken network.
            response = urlreq.urlopen(url, data, 5)
            current_app.logger.debug(
                'Version check HTTP response code: %d' % response.getcode()
            )

            if response.getcode() == 200:
                data = json.loads(response.read().decode('utf-8'))
                current_app.logger.debug('Response data: %s' % data)
        except:
            current_app.logger.exception('Exception when checking for update')

        if data is not None:
            if data['pgadmin4']['version_int'] > config.APP_VERSION_INT:
                msg = render_template(
                    MODULE_NAME + "/upgrade.html",
                    current_version=config.APP_VERSION,
                    upgrade_version=data['pgadmin4']['version'],
                    product_name=config.APP_NAME,
                    download_url=data['pgadmin4']['download_url']
                )

                flash(msg, 'warning')

    response = Response(render_template(
        MODULE_NAME + "/index.html",
        username=current_user.email,
        is_admin=current_user.has_role("Administrator"),
        _=gettext
    ))

    # Set the language cookie after login, so next time the user will have that
    # same option at the login time.
    misc_preference = Preferences.module('miscellaneous')
    user_languages = misc_preference.preference(
        'user_language'
    )
    language = 'en'
    if user_languages:
        language = user_languages.get() or 'en'

    response.set_cookie("PGADMIN_LANGUAGE", language)

    return response


@blueprint.route("/js/utils.js")
@login_required
def utils():
    layout = get_setting('Browser/Layout', default='')
    snippets = []

    prefs = Preferences.module('paths')

    pg_help_path_pref = prefs.preference('pg_help_path')
    pg_help_path = pg_help_path_pref.get()

    edbas_help_path_pref = prefs.preference('edbas_help_path')
    edbas_help_path = edbas_help_path_pref.get()

    # Get sqleditor options
    prefs = Preferences.module('sqleditor')

    editor_tab_size_pref = prefs.preference('tab_size')
    editor_tab_size = editor_tab_size_pref.get()

    editor_use_spaces_pref = prefs.preference('use_spaces')
    editor_use_spaces = editor_use_spaces_pref.get()

    editor_wrap_code_pref = prefs.preference('wrap_code')
    editor_wrap_code = editor_wrap_code_pref.get()

    brace_matching_pref = prefs.preference('brace_matching')
    brace_matching = brace_matching_pref.get()

    insert_pair_brackets_perf = prefs.preference('insert_pair_brackets')
    insert_pair_brackets = insert_pair_brackets_perf.get()

    # This will be opposite of use_space option
    editor_indent_with_tabs = False if editor_use_spaces else True

    # Try to fetch current libpq version from the driver
    try:
        from config import PG_DEFAULT_DRIVER
        from pgadmin.utils.driver import get_driver
        driver = get_driver(PG_DEFAULT_DRIVER)
        pg_libpq_version = driver.libpq_version()
    except:
        pg_libpq_version = 0

    for submodule in current_blueprint.submodules:
        snippets.extend(submodule.jssnippets)
    return make_response(
        render_template(
            'browser/js/utils.js',
            layout=layout,
            jssnippets=snippets,
            pg_help_path=pg_help_path,
            edbas_help_path=edbas_help_path,
            editor_tab_size=editor_tab_size,
            editor_use_spaces=editor_use_spaces,
            editor_wrap_code=editor_wrap_code,
            editor_brace_matching=brace_matching,
            editor_insert_pair_brackets=insert_pair_brackets,
            editor_indent_with_tabs=editor_indent_with_tabs,
            app_name=config.APP_NAME,
            pg_libpq_version=pg_libpq_version
        ),
        200, {'Content-Type': 'application/x-javascript'})


@blueprint.route("/js/endpoints.js")
def exposed_urls():
    return make_response(
        render_template('browser/js/endpoints.js'),
        200, {'Content-Type': 'application/x-javascript'}
    )


@blueprint.route("/js/error.js")
@login_required
def error_js():
    return make_response(
        render_template('browser/js/error.js', _=gettext),
        200, {'Content-Type': 'application/x-javascript'})


@blueprint.route("/js/node.js")
@login_required
def node_js():
    prefs = Preferences.module('paths')

    pg_help_path_pref = prefs.preference('pg_help_path')
    pg_help_path = pg_help_path_pref.get()

    edbas_help_path_pref = prefs.preference('edbas_help_path')
    edbas_help_path = edbas_help_path_pref.get()

    return make_response(
        render_template('browser/js/node.js',
                        pg_help_path=pg_help_path,
                        edbas_help_path=edbas_help_path,
                        _=gettext
                        ),
        200, {'Content-Type': 'application/x-javascript'})


@blueprint.route("/js/messages.js")
def messages_js():
    return make_response(
        render_template('browser/js/messages.js', _=gettext),
        200, {'Content-Type': 'application/x-javascript'})


@blueprint.route("/js/collection.js")
@login_required
def collection_js():
    return make_response(
        render_template('browser/js/collection.js', _=gettext),
        200, {'Content-Type': 'application/x-javascript'})


@blueprint.route("/browser.css")
@login_required
def browser_css():
    """Render and return CSS snippets from the nodes and modules."""
    snippets = []

    # Get configurable options
    prefs = Preferences.module('sqleditor')

    sql_font_size_pref = prefs.preference('sql_font_size')
    sql_font_size = round(float(sql_font_size_pref.get()), 2)

    if sql_font_size != 0:
        snippets.append('.CodeMirror { font-size: %sem; }' % str(sql_font_size))

    for submodule in blueprint.submodules:
        snippets.extend(submodule.csssnippets)
    return make_response(
        render_template(
            'browser/css/browser.css', snippets=snippets, _=gettext
        ),
        200, {'Content-Type': 'text/css'})


@blueprint.route("/nodes/", endpoint="nodes")
@login_required
def get_nodes():
    """Build a list of treeview nodes from the child nodes."""
    nodes = []
    for submodule in current_blueprint.submodules:
        nodes.extend(submodule.get_nodes())

    return make_json_response(data=nodes)

# Only register route if SECURITY_CHANGEABLE is set to True
# We can't access app context here so cannot
# use app.config['SECURITY_CHANGEABLE']
if hasattr(config, 'SECURITY_CHANGEABLE') and config.SECURITY_CHANGEABLE:
    @blueprint.route("/change_password", endpoint="change_password",
                     methods=['GET', 'POST'])
    @login_required
    def change_password():
        """View function which handles a change password request."""

        has_error = False
        form_class = _security.change_password_form

        if request.json:
            form = form_class(MultiDict(request.json))
        else:
            form = form_class()

        if form.validate_on_submit():
            try:
                change_user_password(current_user, form.new_password.data)
            except SOCKETErrorException as e:
                # Handle socket errors which are not covered by SMTPExceptions.
                logging.exception(str(e), exc_info=True)
                flash(gettext(u'SMTP Socket error: {}\nYour password has not been changed.').format(e), 'danger')
                has_error = True
            except (SMTPConnectError, SMTPResponseException,
                    SMTPServerDisconnected, SMTPDataError, SMTPHeloError,
                    SMTPException, SMTPAuthenticationError, SMTPSenderRefused,
                    SMTPRecipientsRefused) as e:
                # Handle smtp specific exceptions.
                logging.exception(str(e), exc_info=True)
                flash(gettext(u'SMTP error: {}\nYour password has not been changed.').format(e), 'danger')
                has_error = True
            except Exception as e:
                # Handle other exceptions.
                logging.exception(str(e), exc_info=True)
                flash(gettext(u'Error: {}\nYour password has not been changed.').format(e), 'danger')
                has_error = True

            if request.json is None and not has_error:
                after_this_request(_commit)
                do_flash(*get_message('PASSWORD_CHANGE'))
                return redirect(get_url(_security.post_change_view) or
                                get_url(_security.post_login_view))

        if request.json and not has_error:
            form.user = current_user
            return _render_json(form)

        return _security.render_template(
            config_value('CHANGE_PASSWORD_TEMPLATE'),
            change_password_form=form,
            **_ctx('change_password'))


# Only register route if SECURITY_RECOVERABLE is set to True
if hasattr(config, 'SECURITY_RECOVERABLE') and config.SECURITY_RECOVERABLE:

    def send_reset_password_instructions(user):
        """Sends the reset password instructions email for the specified user.

        :param user: The user to send the instructions to
        """
        token = generate_reset_password_token(user)
        reset_link = url_for('browser.reset_password', token=token,
                             _external=True)

        send_mail(config_value('EMAIL_SUBJECT_PASSWORD_RESET'), user.email,
                  'reset_instructions',
                  user=user, reset_link=reset_link)

        reset_password_instructions_sent.send(
            current_app._get_current_object(),
            user=user, token=token)


    @blueprint.route("/reset_password", endpoint="forgot_password",
                     methods=['GET', 'POST'])
    @anonymous_user_required
    def forgot_password():
        """View function that handles a forgotten password request."""
        has_error = False
        form_class = _security.forgot_password_form

        if request.json:
            form = form_class(MultiDict(request.json))
        else:
            form = form_class()

        if form.validate_on_submit():
            try:
                send_reset_password_instructions(form.user)
            except SOCKETErrorException as e:
                # Handle socket errors which are not covered by SMTPExceptions.
                logging.exception(str(e), exc_info=True)
                flash(gettext(u'SMTP Socket error: {}\nYour password has not been changed.').format(e), 'danger')
                has_error = True
            except (SMTPConnectError, SMTPResponseException,
                    SMTPServerDisconnected, SMTPDataError, SMTPHeloError,
                    SMTPException, SMTPAuthenticationError, SMTPSenderRefused,
                    SMTPRecipientsRefused) as e:

                # Handle smtp specific exceptions.
                logging.exception(str(e), exc_info=True)
                flash(gettext(u'SMTP error: {}\nYour password has not been changed.').format(e), 'danger')
                has_error = True
            except Exception as e:
                # Handle other exceptions.
                logging.exception(str(e), exc_info=True)
                flash(gettext(u'Error: {}\nYour password has not been changed.').format(e), 'danger')
                has_error = True

            if request.json is None and not has_error:
                do_flash(*get_message('PASSWORD_RESET_REQUEST',
                                      email=form.user.email))

        if request.json and not has_error:
            return _render_json(form, include_user=False)

        return _security.render_template(
            config_value('FORGOT_PASSWORD_TEMPLATE'),
            forgot_password_form=form,
            **_ctx('forgot_password'))


    # We are not in app context so cannot use url_for('browser.forgot_password')
    # So hard code the url '/browser/reset_password' while passing as
    # parameter to slash_url_suffix function.
    @blueprint.route('/reset_password' + slash_url_suffix(
        '/browser/reset_password', '<token>'),
                     methods=['GET', 'POST'],
                     endpoint='reset_password')
    @anonymous_user_required
    def reset_password(token):
        """View function that handles a reset password request."""

        expired, invalid, user = reset_password_token_status(token)

        if invalid:
            do_flash(*get_message('INVALID_RESET_PASSWORD_TOKEN'))
        if expired:
            do_flash(*get_message('PASSWORD_RESET_EXPIRED', email=user.email,
                                  within=_security.reset_password_within))
        if invalid or expired:
            return redirect(url_for('browser.forgot_password'))
        has_error = False
        form = _security.reset_password_form()

        if form.validate_on_submit():
            try:
                update_password(user, form.password.data)
            except SOCKETErrorException as e:
                # Handle socket errors which are not covered by SMTPExceptions.
                logging.exception(str(e), exc_info=True)
                flash(gettext(u'SMTP Socket error: {}\nYour password has not been changed.').format(e), 'danger')
                has_error = True
            except (SMTPConnectError, SMTPResponseException,
                    SMTPServerDisconnected, SMTPDataError, SMTPHeloError,
                    SMTPException, SMTPAuthenticationError, SMTPSenderRefused,
                    SMTPRecipientsRefused) as e:

                # Handle smtp specific exceptions.
                logging.exception(str(e), exc_info=True)
                flash(gettext(u'SMTP error: {}\nYour password has not been changed.').format(e), 'danger')
                has_error = True
            except Exception as e:
                # Handle other exceptions.
                logging.exception(str(e), exc_info=True)
                flash(gettext(u'Error: {}\nYour password has not been changed.').format(e), 'danger')
                has_error = True

            if not has_error:
                after_this_request(_commit)
                do_flash(*get_message('PASSWORD_RESET'))
                login_user(user)
                return redirect(get_url(_security.post_reset_view) or
                                get_url(_security.post_login_view))

        return _security.render_template(
            config_value('RESET_PASSWORD_TEMPLATE'),
            reset_password_form=form,
            reset_password_token=token,
            **_ctx('reset_password'))
