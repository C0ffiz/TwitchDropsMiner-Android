"""UI Screens for TwitchDropsMiner Android - KivyMD 2.0"""
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
        settings_btn.bind(on_release=lambda x: self.app.screen_manager.switch_to(self.app.screen_manager.get_screen('settings')))
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
        self.progress_bar = MDLinearProgressIndicator(value=self.progress_value, size_hint_y=None, height=dp(4))
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
        inv_btn = MDButton(style="text", on_release=lambda x: self.app.screen_manager.switch_to(self.app.screen_manager.get_screen('inventory')))
        inv_btn.add_widget(MDButtonText(text="Inventory"))
        nav_buttons.add_widget(inv_btn)
        ch_btn = MDButton(style="text", on_release=lambda x: self.app.screen_manager.switch_to(self.app.screen_manager.get_screen('channels')))
        ch_btn.add_widget(MDButtonText(text="Channels"))
        nav_buttons.add_widget(ch_btn)
        log_btn = MDButton(style="text", on_release=lambda x: self.app.screen_manager.switch_to(self.app.screen_manager.get_screen('logs')))
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
        self.layout.add_widget(content)

    def do_login(self, *args):
        token = self.token_field.text.strip()
        if token:
            self.app.login(token)


class InventoryScreen(BaseScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_toolbar("Inventory", leading_icon="arrow-left", leading_callback=lambda x: self.app.screen_manager.switch_to(self.app.screen_manager.get_screen('home')))
        scroll = ScrollView()
        self.list_view = MDList()
        scroll.add_widget(self.list_view)
        self.layout.add_widget(scroll)

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
        self.add_toolbar("Channels", leading_icon="arrow-left", leading_callback=lambda x: self.app.screen_manager.switch_to(self.app.screen_manager.get_screen('home')))
        scroll = ScrollView()
        self.list_view = MDList()
        scroll.add_widget(self.list_view)
        self.layout.add_widget(scroll)
        item = MDListItem()
        item.add_widget(MDListItemHeadlineText(text="No channels loaded"))
        self.list_view.add_widget(item)


class SettingsScreen(BaseScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_toolbar("Settings", leading_icon="arrow-left", leading_callback=lambda x: self.app.screen_manager.switch_to(self.app.screen_manager.get_screen('home')))
        scroll = ScrollView()
        content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(16), size_hint_y=None)
        content.bind(minimum_height=content.setter('height'))

        auto_claim_box = BoxLayout(size_hint_y=None, height=dp(50))
        auto_claim_box.add_widget(MDLabel(text="Auto Claim Drops"))
        auto_claim_switch = MDSwitch()
        auto_claim_switch.active = self.app.settings.auto_claim
        auto_claim_switch.bind(active=self.on_auto_claim_change)
        auto_claim_box.add_widget(auto_claim_switch)
        content.add_widget(auto_claim_box)

        notif_box = BoxLayout(size_hint_y=None, height=dp(50))
        notif_box.add_widget(MDLabel(text="Notifications"))
        notif_switch = MDSwitch()
        notif_switch.active = self.app.settings.notifications_enabled
        notif_switch.bind(active=self.on_notifications_change)
        notif_box.add_widget(notif_switch)
        content.add_widget(notif_box)

        logout_btn = MDButton(size_hint_y=None, height=dp(50), on_release=lambda x: self.app.logout())
        logout_btn.add_widget(MDButtonText(text="Logout"))
        content.add_widget(logout_btn)

        scroll.add_widget(content)
        self.layout.add_widget(scroll)

    def on_auto_claim_change(self, instance, value):
        self.app.settings.auto_claim = value
        self.app.settings.save()

    def on_notifications_change(self, instance, value):
        self.app.settings.notifications_enabled = value
        self.app.settings.save()


class LogsScreen(BaseScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        toolbar = MDTopAppBar()
        toolbar.add_widget(MDTopAppBarTitle(text="Logs"))
        leading = MDTopAppBarLeadingButtonContainer()
        back_btn = MDActionTopAppBarButton(icon="arrow-left")
        back_btn.bind(on_release=lambda x: self.app.screen_manager.switch_to(self.app.screen_manager.get_screen('home')))
        leading.add_widget(back_btn)
        toolbar.add_widget(leading)
        trailing = MDTopAppBarTrailingButtonContainer()
        clear_btn = MDActionTopAppBarButton(icon="delete")
        clear_btn.bind(on_release=self.clear_logs)
        trailing.add_widget(clear_btn)
        toolbar.add_widget(trailing)
        self.layout.add_widget(toolbar)
        scroll = ScrollView()
        self.list_view = MDList()
        scroll.add_widget(self.list_view)
        self.layout.add_widget(scroll)

    def add_log(self, message):
        item = MDListItem()
        item.add_widget(MDListItemHeadlineText(text=message))
        self.list_view.add_widget(item)

    def clear_logs(self, *args):
        self.list_view.clear_widgets()
        self.app.logs.clear()
