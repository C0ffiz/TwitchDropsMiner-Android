"""UI Screens for TwitchDropsMiner Android - KivyMD 2.0"""
from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.properties import StringProperty, NumericProperty
from kivy.metrics import dp
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.textfield import MDTextField
from kivymd.uix.appbar import MDTopAppBar, MDTopAppBarTitle, MDTopAppBarLeadingButtonContainer, MDTopAppBarTrailingButtonContainer, MDActionTopAppBarButton
from kivymd.uix.list import MDList, MDListItem, MDListItemHeadlineText, MDListItemSupportingText
from kivymd.uix.progressindicator import MDLinearProgressIndicator
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


class HomeScreen(BaseScreen):
    status_text = StringProperty("Idle")
    channel_text = StringProperty("None")
    drop_text = StringProperty("No active drop")
    progress_value = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        toolbar = MDTopAppBar()
        toolbar.add_widget(MDTopAppBarTitle(text="TwitchDropsMiner"))
        trailing = MDTopAppBarTrailingButtonContainer()
        settings_btn = MDActionTopAppBarButton(icon="cog")
        settings_btn.bind(on_release=lambda x: setattr(self.app.screen_manager, 'current', 'settings'))
        trailing.add_widget(settings_btn)
        toolbar.add_widget(trailing)
        self.layout.add_widget(toolbar)

        content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(16))

        status_card = MDCard(orientation='vertical', padding=dp(16), spacing=dp(8), size_hint_y=None, height=dp(150))
        status_card.add_widget(MDLabel(text="Status", font_style="Title", role="large"))
        self.status_label = MDLabel(text=self.status_text)
        status_card.add_widget(self.status_label)
        status_card.add_widget(MDLabel(text="Channel", font_style="Label", role="small"))
        self.channel_label = MDLabel(text=self.channel_text)
        status_card.add_widget(self.channel_label)
        content.add_widget(status_card)

        drop_card = MDCard(orientation='vertical', padding=dp(16), spacing=dp(8), size_hint_y=None, height=dp(150))
        drop_card.add_widget(MDLabel(text="Current Drop", font_style="Title", role="large"))
        self.drop_label = MDLabel(text=self.drop_text)
        drop_card.add_widget(self.drop_label)
        self.progress_bar = MDLinearProgressIndicator(size_hint_y=None, height=dp(4))
        drop_card.add_widget(self.progress_bar)
        content.add_widget(drop_card)

        buttons = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(8))
        self.start_btn = MDButton(on_release=lambda x: self.app.start_mining())
        self.start_btn.add_widget(MDButtonText(text="Start"))
        buttons.add_widget(self.start_btn)
        self.stop_btn = MDButton(on_release=lambda x: self.app.stop_mining())
        self.stop_btn.add_widget(MDButtonText(text="Stop"))
        buttons.add_widget(self.stop_btn)
        content.add_widget(buttons)

        nav_buttons = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(8))
        inv_btn = MDButton(style="text", on_release=lambda x: setattr(self.app.screen_manager, 'current', 'inventory'))
        inv_btn.add_widget(MDButtonText(text="Inventory"))
        nav_buttons.add_widget(inv_btn)
        ch_btn = MDButton(style="text", on_release=lambda x: setattr(self.app.screen_manager, 'current', 'channels'))
        ch_btn.add_widget(MDButtonText(text="Channels"))
        nav_buttons.add_widget(ch_btn)
        log_btn = MDButton(style="text", on_release=lambda x: setattr(self.app.screen_manager, 'current', 'logs'))
        log_btn.add_widget(MDButtonText(text="Logs"))
        nav_buttons.add_widget(log_btn)
        content.add_widget(nav_buttons)

        self.layout.add_widget(content)

    def update_status(self, status):
        self.status_text = status
        self.status_label.text = status

    def update_channel(self, channel):
        self.channel_text = channel
        self.channel_label.text = channel

    def update_drop(self, drop):
        if drop:
            self.drop_text = str(drop)
            # Android-specific: compute progress from TimedDrop minutes; guard against zero
            if drop.required_minutes > 0:
                self.progress_value = (drop.current_minutes / drop.required_minutes) * 100
            else:
                self.progress_value = 0
        else:
            self.drop_text = "No active drop"
            self.progress_value = 0
        self.drop_label.text = self.drop_text
        self.progress_bar.value = self.progress_value

    def update_progress(self, current, total):
        if total > 0:
            self.progress_value = (current / total) * 100
            self.progress_bar.value = self.progress_value

    def on_enter(self, *args):
        # Android-specific: re-sync drop and channel when returning to HomeScreen
        # (e.g. after background resume or navigation from another screen)
        tc = self.app.twitch_client
        if tc is None:
            return
        self.update_drop(tc.current_drop)
        # Android-specific: get_with_default returns Channel or None; extract display_name for the label
        ch = tc.watching_channel.get_with_default(None)
        self.update_channel(ch.display_name if ch else "")


class LoginScreen(BaseScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_toolbar("Login")
        content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(16))
        content.add_widget(MDLabel(text="TwitchDropsMiner", font_style="Display", role="small", halign="center", size_hint_y=None, height=dp(50)))
        content.add_widget(MDLabel(text="Enter your Twitch OAuth token to login", halign="center", size_hint_y=None, height=dp(40)))
        self.token_field = MDTextField(hint_text="OAuth Token")
        self.token_field.password = True
        content.add_widget(self.token_field)
        login_btn = MDButton(size_hint_y=None, height=dp(50), on_release=self.do_login)
        login_btn.add_widget(MDButtonText(text="Login"))
        content.add_widget(login_btn)
        content.add_widget(MDLabel(text="1. Visit twitchtokengenerator.com\n2. Select Custom Scope Token\n3. Generate and paste here", size_hint_y=None, height=dp(80)))
        self.error_label = MDLabel(text="", theme_text_color="Error", size_hint_y=None, height=dp(40))
        content.add_widget(self.error_label)
        self.layout.add_widget(content)

    def show_error(self, message: str):
        self.error_label.text = message

    def do_login(self, *args):
        token = self.token_field.text.strip()
        if token:
            self.app.login(token)


class InventoryScreen(BaseScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_toolbar("Inventory", leading_icon="arrow-left", leading_callback=lambda x: setattr(self.manager, 'current', 'home'))
        scroll = ScrollView()
        self.list_view = MDList()
        scroll.add_widget(self.list_view)
        self.layout.add_widget(scroll)

    def on_enter(self, *args):
        # Android-specific: refresh inventory list every time the screen is entered
        # so stale state after background resume or first open before callback fires is corrected
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
            item.add_widget(MDListItemSupportingText(text=str(campaign.game.name)))
            self.list_view.add_widget(item)


class ChannelsScreen(BaseScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_toolbar("Channels", leading_icon="arrow-left", leading_callback=lambda x: setattr(self.manager, 'current', 'home'))
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
            item.add_widget(MDListItemHeadlineText(text=channel.name))
            viewers = channel._stream.viewers if channel._stream else 0
            item.add_widget(MDListItemSupportingText(text=f"Viewers: {viewers}"))
            self.list_view.add_widget(item)


class SettingsScreen(BaseScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_toolbar("Settings", leading_icon="arrow-left", leading_callback=lambda x: setattr(self.manager, 'current', 'home'))
        scroll = ScrollView()
        content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(16), size_hint_y=None)
        content.bind(minimum_height=content.setter('height'))

        auto_claim_box = BoxLayout(size_hint_y=None, height=dp(50))
        auto_claim_box.add_widget(MDLabel(text="Auto Claim Drops"))
        self.auto_claim_switch = MDSwitch()
        # Android-specific: active state set in on_enter(); App.get_running_app() may be None here
        self.auto_claim_switch.bind(active=self.on_auto_claim_change)
        auto_claim_box.add_widget(self.auto_claim_switch)
        content.add_widget(auto_claim_box)

        notif_box = BoxLayout(size_hint_y=None, height=dp(50))
        notif_box.add_widget(MDLabel(text="Notifications"))
        self.notif_switch = MDSwitch()
        # Android-specific: active state set in on_enter(); App.get_running_app() may be None here
        self.notif_switch.bind(active=self.on_notifications_change)
        notif_box.add_widget(self.notif_switch)
        content.add_widget(notif_box)

        logout_btn = MDButton(size_hint_y=None, height=dp(50), on_release=lambda x: self.app.logout())
        logout_btn.add_widget(MDButtonText(text="Logout"))
        content.add_widget(logout_btn)

        scroll.add_widget(content)
        self.layout.add_widget(scroll)
        self._loading = False  # Android-specific: guard against save() on programmatic active changes

    def on_enter(self, *args):
        # Android-specific: read settings here, not in __init__, to avoid None app during construction
        # _loading prevents on_auto_claim_change / on_notifications_change from calling save() here
        self._loading = True
        settings = self.app.settings
        self.auto_claim_switch.active = settings.auto_claim
        self.notif_switch.active = settings.notifications_enabled
        self._loading = False

    def on_auto_claim_change(self, instance, value):
        if self._loading:  # Android-specific: skip save during programmatic on_enter sync
            return
        self.app.settings.auto_claim = value
        self.app.settings.save()

    def on_notifications_change(self, instance, value):
        if self._loading:  # Android-specific: skip save during programmatic on_enter sync
            return
        self.app.settings.notifications_enabled = value
        self.app.settings.save()


class LogsScreen(BaseScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        toolbar = MDTopAppBar()
        toolbar.add_widget(MDTopAppBarTitle(text="Logs"))
        leading = MDTopAppBarLeadingButtonContainer()
        back_btn = MDActionTopAppBarButton(icon="arrow-left")
        back_btn.bind(on_release=lambda x: setattr(self.manager, 'current', 'home'))
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
