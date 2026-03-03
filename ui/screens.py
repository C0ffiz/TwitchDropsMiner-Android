"""UI Screens for TwitchDropsMiner Android - KivyMD 2.0"""
from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.appbar import MDTopAppBar, MDTopAppBarTitle, MDTopAppBarLeadingButtonContainer, MDTopAppBarTrailingButtonContainer, MDActionTopAppBarButton
from kivymd.uix.list import MDList, MDListItem, MDListItemHeadlineText, MDListItemSupportingText
from kivymd.uix.navigationbar import MDNavigationBar, MDNavigationItem, MDNavigationItemIcon, MDNavigationItemLabel
from kivymd.uix.progressindicator import MDLinearProgressIndicator
from kivymd.uix.screen import MDScreen
from kivymd.uix.screenmanager import MDScreenManager
from kivymd.uix.selectioncontrol import MDSwitch


class BaseScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = BoxLayout(orientation='vertical')
        self.add_widget(self.layout)

    def add_toolbar(self, title, leading_icon=None, leading_callback=None):
        toolbar = MDTopAppBar()
        toolbar.add_widget(MDTopAppBarTitle(text=title))
        if leading_icon and leading_callback:
            leading = MDTopAppBarLeadingButtonContainer()
            btn = MDActionTopAppBarButton(icon=leading_icon)
            btn.bind(on_release=leading_callback)
            leading.add_widget(btn)
            toolbar.add_widget(leading)
        self.layout.add_widget(toolbar)
        return toolbar

    @property
    def app(self):
        from kivy.app import App
        return App.get_running_app()


class _NavItem(MDNavigationItem):
    """Helper: MDNavigationItem with icon + label pre-built (Python-only, no KV)."""

    def __init__(self, icon: str, text: str, **kwargs):
        super().__init__(**kwargs)
        self.add_widget(MDNavigationItemIcon(icon=icon))
        self.add_widget(MDNavigationItemLabel(text=text))


class TabScreen(MDScreen):
    """Base class for all MDNavigationBar tab screens.

    Provides the `app` property and a vertical BoxLayout (`self.layout`)
    into which subclasses add their content widgets.
    """

    @property
    def app(self):
        from kivy.app import App
        return App.get_running_app()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = BoxLayout(orientation='vertical')
        self.add_widget(self.layout)


class MainTabScreen(TabScreen):
    """Tab 1 — Mining status, active channel, drop progress, Start/Stop buttons."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Toolbar with trailing icons to open secondary screens
        toolbar = MDTopAppBar()
        toolbar.add_widget(MDTopAppBarTitle(text="TwitchDropsMiner"))
        trailing = MDTopAppBarTrailingButtonContainer()
        ch_btn = MDActionTopAppBarButton(icon="account-multiple")
        ch_btn.bind(on_release=lambda x: setattr(self.app.screen_manager, 'current', 'channels'))
        trailing.add_widget(ch_btn)
        log_btn = MDActionTopAppBarButton(icon="text-box-outline")
        log_btn.bind(on_release=lambda x: setattr(self.app.screen_manager, 'current', 'logs'))
        trailing.add_widget(log_btn)
        toolbar.add_widget(trailing)
        self.layout.add_widget(toolbar)

        scroll = ScrollView()
        content = BoxLayout(
            orientation='vertical', padding=dp(16), spacing=dp(16), size_hint_y=None
        )
        content.bind(minimum_height=content.setter('height'))

        # Status + channel card
        status_card = MDCard(
            orientation='vertical', padding=dp(16), spacing=dp(4),
            size_hint_y=None, height=dp(140)
        )
        status_card.add_widget(MDLabel(text="Status", font_style="Label", role="small"))
        self.status_label = MDLabel(text="Idle", size_hint_y=None, height=dp(32))
        status_card.add_widget(self.status_label)
        status_card.add_widget(MDLabel(text="Channel", font_style="Label", role="small"))
        self.channel_label = MDLabel(text="None", size_hint_y=None, height=dp(32))
        status_card.add_widget(self.channel_label)
        content.add_widget(status_card)

        # Active drop card
        drop_card = MDCard(
            orientation='vertical', padding=dp(16), spacing=dp(8),
            size_hint_y=None, height=dp(120)
        )
        drop_card.add_widget(MDLabel(text="Current Drop", font_style="Label", role="small"))
        self.drop_label = MDLabel(text="No active drop", size_hint_y=None, height=dp(32))
        drop_card.add_widget(self.drop_label)
        self.progress_bar = MDLinearProgressIndicator(size_hint_y=None, height=dp(8), value=0)
        drop_card.add_widget(self.progress_bar)
        content.add_widget(drop_card)

        # Start / Stop buttons
        buttons = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(8))
        start_btn = MDButton(on_release=lambda x: self.app.start_mining())
        start_btn.add_widget(MDButtonText(text="Start Mining"))
        buttons.add_widget(start_btn)
        stop_btn = MDButton(on_release=lambda x: self.app.stop_mining())
        stop_btn.add_widget(MDButtonText(text="Stop Mining"))
        buttons.add_widget(stop_btn)
        content.add_widget(buttons)

        scroll.add_widget(content)
        self.layout.add_widget(scroll)

    def on_enter(self, *args):
        tc = self.app.twitch_client
        if tc is None:
            return
        self.update_drop(tc.current_drop)
        ch = tc.watching_channel.get_with_default(None)
        self.update_channel(ch.display_name if ch else "")

    def update_status(self, status: str):
        self.status_label.text = status

    def update_channel(self, channel_name: str):
        self.channel_label.text = channel_name or "None"

    def update_drop(self, drop):
        if drop:
            self.drop_label.text = str(drop)
            self.progress_bar.value = (
                min(drop.current_minutes / drop.required_minutes, 1.0) * 100
                if drop.required_minutes > 0 else 0
            )
        else:
            self.drop_label.text = "No active drop"
            self.progress_bar.value = 0

    def update_progress(self, current: int, total: int):
        if total > 0:
            self.progress_bar.value = (current / total) * 100


class InventoryTabScreen(TabScreen):
    """Tab 2 — Scrollable list of drop campaigns with status."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        toolbar = MDTopAppBar()
        toolbar.add_widget(MDTopAppBarTitle(text="Inventory"))
        self.layout.add_widget(toolbar)
        scroll = ScrollView()
        self.list_view = MDList()
        scroll.add_widget(self.list_view)
        self.layout.add_widget(scroll)

    def on_enter(self, *args):
        # Android-specific: refresh on enter in case the callback fired before this tab was visible
        tc = self.app.twitch_client
        if tc is None:
            return
        self.update_inventory(tc.inventory)

    def update_inventory(self, inventory):
        self.list_view.clear_widgets()
        if not inventory:
            item = MDListItem()
            item.add_widget(MDListItemHeadlineText(text="No campaigns available"))
            self.list_view.add_widget(item)
            return
        for campaign in inventory:
            item = MDListItem()
            item.add_widget(MDListItemHeadlineText(text=str(campaign.name)))
            supporting = f"{campaign.game.name} \u2014 {campaign.status_text}"
            item.add_widget(MDListItemSupportingText(text=supporting))
            self.list_view.add_widget(item)


class SettingsTabScreen(TabScreen):
    """Tab 3 — Auto-claim + notifications toggles, account info, logout."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        toolbar = MDTopAppBar()
        toolbar.add_widget(MDTopAppBarTitle(text="Settings"))
        self.layout.add_widget(toolbar)

        scroll = ScrollView()
        content = BoxLayout(
            orientation='vertical', padding=dp(16), spacing=dp(16), size_hint_y=None
        )
        content.bind(minimum_height=content.setter('height'))

        self.username_label = MDLabel(
            text="Not logged in", halign="center", size_hint_y=None, height=dp(40)
        )
        content.add_widget(self.username_label)

        auto_claim_row = BoxLayout(size_hint_y=None, height=dp(50))
        auto_claim_row.add_widget(MDLabel(text="Auto Claim Drops"))
        self.auto_claim_switch = MDSwitch()
        self.auto_claim_switch.bind(active=self._on_auto_claim_change)
        auto_claim_row.add_widget(self.auto_claim_switch)
        content.add_widget(auto_claim_row)

        notif_row = BoxLayout(size_hint_y=None, height=dp(50))
        notif_row.add_widget(MDLabel(text="Notifications"))
        self.notif_switch = MDSwitch()
        self.notif_switch.bind(active=self._on_notifications_change)
        notif_row.add_widget(self.notif_switch)
        content.add_widget(notif_row)

        logout_btn = MDButton(
            size_hint_y=None, height=dp(50), on_release=lambda x: self.app.logout()
        )
        logout_btn.add_widget(MDButtonText(text="Logout"))
        content.add_widget(logout_btn)

        scroll.add_widget(content)
        self.layout.add_widget(scroll)
        self._loading = False  # guard: skip save() during programmatic switch sync

    def on_enter(self, *args):
        # Android-specific: read settings here not in __init__ to avoid None app at construction
        self._loading = True
        settings = self.app.settings
        username = getattr(settings, 'username', '') or ''
        self.username_label.text = f"Logged in as: {username}" if username else "Not logged in"
        self.auto_claim_switch.active = getattr(settings, 'auto_claim', True)
        self.notif_switch.active = getattr(settings, 'notifications_enabled', True)
        self._loading = False

    def _on_auto_claim_change(self, instance, value):
        if self._loading:
            return
        self.app.settings.auto_claim = value
        self.app.settings.save()

    def _on_notifications_change(self, instance, value):
        if self._loading:
            return
        self.app.settings.notifications_enabled = value
        self.app.settings.save()


class HelpTabScreen(TabScreen):
    """Tab 4 — Static how-to text and app version info."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        toolbar = MDTopAppBar()
        toolbar.add_widget(MDTopAppBarTitle(text="Help"))
        self.layout.add_widget(toolbar)

        scroll = ScrollView()
        content = BoxLayout(
            orientation='vertical', padding=dp(16), spacing=dp(16), size_hint_y=None
        )
        content.bind(minimum_height=content.setter('height'))

        from core.version import __version__
        content.add_widget(MDLabel(
            text=f"TwitchDropsMiner Android v{__version__}",
            font_style="Title", role="large",
            halign="center", size_hint_y=None, height=dp(50)
        ))
        help_text = (
            "1. The app starts the Twitch device code login flow automatically.\n"
            "   Enter the code shown on your Twitch account page.\n\n"
            "2. Once logged in, the app searches for channels\n"
            "   with active Drop campaigns and watches them.\n\n"
            "3. Enable Auto Claim in Settings to automatically\n"
            "   collect drops when they complete.\n\n"
            "4. Use the Inventory tab to track drop progress.\n\n"
            "5. Tap the icons in the Main tab toolbar to view\n"
            "   active channels or the event log."
        )
        content.add_widget(MDLabel(
            text=help_text, size_hint_y=None, adaptive_height=True
        ))
        github_btn = MDButton(
            size_hint_y=None, height=dp(50), on_release=self._open_github
        )
        github_btn.add_widget(MDButtonText(text="Open on GitHub"))
        content.add_widget(github_btn)

        scroll.add_widget(content)
        self.layout.add_widget(scroll)

    def _open_github(self, *args):
        import webbrowser
        webbrowser.open("https://github.com/C0ffiz/TwitchDropsMiner-Android")


class LoginScreen(BaseScreen):
    """Full-screen login overlay using device code OAuth flow.

    show_login_code() is called by main.py on_login_code callback when
    TwitchClient receives a device code from the Twitch API.  The full UI
    redesign happens in S16; this stub keeps imports working for S14/S15.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_toolbar("Login")
        content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(16))
        content.add_widget(MDLabel(
            text="TwitchDropsMiner", font_style="Display", role="small",
            halign="center", size_hint_y=None, height=dp(50)
        ))
        self.instruction_label = MDLabel(
            text="Press \"Login with Twitch\" to begin.",
            halign="center", size_hint_y=None, height=dp(40)
        )
        content.add_widget(self.instruction_label)
        # Code display — shown once TwitchClient fires on_login_code
        self.code_label = MDLabel(
            text="", font_style="Display", role="small",
            halign="center", size_hint_y=None, height=dp(70)
        )
        content.add_widget(self.code_label)
        self.open_btn = MDButton(
            size_hint_y=None, height=dp(50), on_release=self._open_browser
        )
        self.open_btn.add_widget(MDButtonText(text="Open Twitch Website"))
        self.open_btn.opacity = 0
        self.open_btn.disabled = True
        content.add_widget(self.open_btn)
        self.status_label = MDLabel(
            text="", halign="center", size_hint_y=None, height=dp(40)
        )
        content.add_widget(self.status_label)
        self.layout.add_widget(content)
        self._verification_uri = ""

    def show_login_code(self, user_code: str, verification_uri: str):
        """Display the device activation code and enable the browser button."""
        self._verification_uri = verification_uri
        self.instruction_label.text = "Visit the link below and enter the code:"
        self.code_label.text = user_code
        self.status_label.text = "Waiting for activation\u2026"
        self.open_btn.opacity = 1
        self.open_btn.disabled = False

    def _open_browser(self, *args):
        import webbrowser
        if self._verification_uri:
            webbrowser.open(self._verification_uri)


class ChannelsScreen(BaseScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_toolbar("Channels", leading_icon="arrow-left", leading_callback=lambda x: setattr(self.manager, 'current', 'app'))
        scroll = ScrollView()
        self.list_view = MDList()
        scroll.add_widget(self.list_view)
        self.layout.add_widget(scroll)

    def on_enter(self, *args):
        # Android-specific: rebuild on enter in case user opens screen before push callback fires
        channels = self.app.twitch_client.channels if self.app.twitch_client else {}
        self.update_channels(channels)

    def update_channels(self, channels):
        # Android-specific: called by main.py on_channels when fetch completes; rebuilds list on main thread
        self.list_view.clear_widgets()
        if not channels:
            item = MDListItem()
            item.add_widget(MDListItemHeadlineText(text="No channels loaded"))
            self.list_view.add_widget(item)
            return
        for channel in channels.values():
            item = MDListItem()
            item.add_widget(MDListItemHeadlineText(text=channel.display_name))
            item.add_widget(MDListItemSupportingText(text=channel.status_text))
            self.list_view.add_widget(item)


class LogsScreen(BaseScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        toolbar = MDTopAppBar()
        toolbar.add_widget(MDTopAppBarTitle(text="Logs"))
        leading = MDTopAppBarLeadingButtonContainer()
        back_btn = MDActionTopAppBarButton(icon="arrow-left")
        back_btn.bind(on_release=lambda x: setattr(self.manager, 'current', 'app'))
        leading.add_widget(back_btn)
        toolbar.add_widget(leading)
        trailing = MDTopAppBarTrailingButtonContainer()
        clear_btn = MDActionTopAppBarButton(icon="delete")
        clear_btn.bind(on_release=self.clear_logs)
        trailing.add_widget(clear_btn)
        toolbar.add_widget(trailing)
        self.layout.add_widget(toolbar)
        scroll = ScrollView()
        self.scroll_view = scroll  # Android-specific: stored for auto-scroll in add_log/on_enter
        self.list_view = MDList()
        scroll.add_widget(self.list_view)
        self.layout.add_widget(scroll)

    def on_enter(self, *args):
        # Android-specific: pre-populate from buffered logs if screen is opened for the first time
        if not self.list_view.children:
            for msg in self.app.logs:
                item = MDListItem()
                item.add_widget(MDListItemHeadlineText(text=msg))
                self.list_view.add_widget(item)
            if self.list_view.children:
                # children[0] is the last-added widget in Kivy — scroll to newest entry
                Clock.schedule_once(
                    lambda dt: self.scroll_view.scroll_to(self.list_view.children[0])
                )

    def add_log(self, message):
        item = MDListItem()
        item.add_widget(MDListItemHeadlineText(text=message))
        self.list_view.add_widget(item)
        # Android-specific: scroll to newest entry after layout pass
        Clock.schedule_once(lambda dt, i=item: self.scroll_view.scroll_to(i))

    def clear_logs(self, *args):
        self.list_view.clear_widgets()
        self.app.logs.clear()


class AppScreen(Screen):
    """Post-login full-screen shell with MDNavigationBar bottom navigation (Phase 1).

    Structure (follows KivyMD 2.x declarative-Python example exactly):
        MDBoxLayout (vertical)
        ├── MDScreenManager  — hosts MainTabScreen, InventoryTabScreen,
        │                       SettingsTabScreen, HelpTabScreen
        └── MDNavigationBar  — 4 items; MDNavigationBar KV sets size_hint_y=None
                               and height=80dp automatically

    update_*() methods delegate to the appropriate tab screen so that
    main.py callbacks can route here without knowing the tab structure.
    """

    @property
    def app(self):
        from kivy.app import App
        return App.get_running_app()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # MDBoxLayout mirrors the KivyMD official example: screen manager
        # expands (size_hint_y=1) and nav bar self-sizes (size_hint_y=None via KV).
        outer = MDBoxLayout(orientation='vertical')
        self.add_widget(outer)

        self.tab_manager = MDScreenManager()
        self.main_tab = MainTabScreen(name='main')
        self.inventory_tab = InventoryTabScreen(name='inventory')
        self.settings_tab = SettingsTabScreen(name='settings')
        self.help_tab = HelpTabScreen(name='help')
        for tab in (self.main_tab, self.inventory_tab, self.settings_tab, self.help_tab):
            self.tab_manager.add_widget(tab)
        outer.add_widget(self.tab_manager)

        # MDNavigationBar.__init__ does not accept positional children (Kivy Widget API);
        # items must be added via add_widget() after construction.
        nav_bar = MDNavigationBar(on_switch_tabs=self._on_switch_tabs)
        for _item in (
            _NavItem(icon='home', text='Main', active=True),
            _NavItem(icon='gift-outline', text='Inventory'),
            _NavItem(icon='cog', text='Settings'),
            _NavItem(icon='help-circle', text='Help'),
        ):
            nav_bar.add_widget(_item)
        outer.add_widget(nav_bar)

    def _on_switch_tabs(self, bar, item, item_icon, item_text):
        """Switch inner tab manager when the user taps a navigation bar item."""
        self.tab_manager.current = item_text.lower()

    # --- Callback delegation (called by main.py) ---

    def update_status(self, status: str):
        self.main_tab.update_status(status)

    def update_channel(self, channel_name: str):
        self.main_tab.update_channel(channel_name)

    def update_drop(self, drop):
        self.main_tab.update_drop(drop)

    def update_progress(self, current: int, total: int):
        self.main_tab.update_progress(current, total)

    def update_inventory(self, inventory):
        self.inventory_tab.update_inventory(inventory)
