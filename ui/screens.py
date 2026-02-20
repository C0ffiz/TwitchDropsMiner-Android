"""UI Screens for TwitchDropsMiner Android"""
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.properties import StringProperty, NumericProperty, ObjectProperty
from kivy.metrics import dp

from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDRaisedButton, MDFlatButton
from kivymd.uix.textfield import MDTextField
from kivymd.uix.toolbar import MDTopAppBar
from kivymd.uix.list import MDList, OneLineListItem, TwoLineListItem, ThreeLineListItem
from kivymd.uix.progressbar import MDProgressBar
from kivymd.uix.selectioncontrol import MDSwitch


class BaseScreen(Screen):
    """Base screen with toolbar."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = BoxLayout(orientation='vertical')
        self.add_widget(self.layout)

    def add_toolbar(self, title: str, left_action=None):
        """Add toolbar to screen."""
        toolbar = MDTopAppBar(title=title)

        if left_action:
            toolbar.left_action_items = [["menu", left_action]]

        self.layout.add_widget(toolbar)
        return toolbar

    @property
    def app(self):
        """Get app instance."""
        from kivy.app import App
        return App.get_running_app()


class HomeScreen(BaseScreen):
    """Main home screen."""

    status_text = StringProperty("Idle")
    channel_text = StringProperty("None")
    drop_text = StringProperty("No active drop")
    progress_value = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Toolbar
        toolbar = self.add_toolbar("TwitchDropsMiner")
        toolbar.right_action_items = [
            ["cog", lambda x: self.app.screen_manager.switch_to(self.app.screen_manager.get_screen('settings'))],
        ]

        # Content
        content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(16))

        # Status card
        status_card = MDCard(
            orientation='vertical',
            padding=dp(16),
            spacing=dp(8),
            size_hint_y=None,
            height=dp(150)
        )
        status_card.add_widget(MDLabel(text="Status", font_style="H6"))
        self.status_label = MDLabel(text=self.status_text)
        status_card.add_widget(self.status_label)

        status_card.add_widget(MDLabel(text="Channel", font_style="Caption"))
        self.channel_label = MDLabel(text=self.channel_text)
        status_card.add_widget(self.channel_label)

        content.add_widget(status_card)

        # Drop card
        drop_card = MDCard(
            orientation='vertical',
            padding=dp(16),
            spacing=dp(8),
            size_hint_y=None,
            height=dp(150)
        )
        drop_card.add_widget(MDLabel(text="Current Drop", font_style="H6"))
        self.drop_label = MDLabel(text=self.drop_text)
        drop_card.add_widget(self.drop_label)

        self.progress_bar = MDProgressBar(value=self.progress_value, size_hint_y=None, height=dp(4))
        drop_card.add_widget(self.progress_bar)

        content.add_widget(drop_card)

        # Buttons
        buttons = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(8))

        self.start_btn = MDRaisedButton(
            text="Start",
            on_release=lambda x: self.app.start_mining()
        )
        buttons.add_widget(self.start_btn)

        self.stop_btn = MDRaisedButton(
            text="Stop",
            on_release=lambda x: self.app.stop_mining()
        )
        buttons.add_widget(self.stop_btn)

        content.add_widget(buttons)

        # Navigation buttons
        nav_buttons = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(8))

        nav_buttons.add_widget(MDFlatButton(
            text="Inventory",
            on_release=lambda x: self.app.screen_manager.switch_to(self.app.screen_manager.get_screen('inventory'))
        ))

        nav_buttons.add_widget(MDFlatButton(
            text="Channels",
            on_release=lambda x: self.app.screen_manager.switch_to(self.app.screen_manager.get_screen('channels'))
        ))

        nav_buttons.add_widget(MDFlatButton(
            text="Logs",
            on_release=lambda x: self.app.screen_manager.switch_to(self.app.screen_manager.get_screen('logs'))
        ))

        content.add_widget(nav_buttons)

        self.layout.add_widget(content)

    def update_status(self, status: str):
        """Update status text."""
        self.status_text = status
        self.status_label.text = status

    def update_channel(self, channel: str):
        """Update channel text."""
        self.channel_text = channel
        self.channel_label.text = channel

    def update_drop(self, drop):
        """Update drop information."""
        if drop:
            self.drop_text = f"{drop.name}\n{drop.current_minutes}/{drop.required_minutes} min"
            self.progress_value = drop.progress * 100
        else:
            self.drop_text = "No active drop"
            self.progress_value = 0

        self.drop_label.text = self.drop_text
        self.progress_bar.value = self.progress_value

    def update_progress(self, args):
        """Update progress bar."""
        current, total = args
        if total > 0:
            self.progress_value = (current / total) * 100
            self.progress_bar.value = self.progress_value


class LoginScreen(BaseScreen):
    """Login screen."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Toolbar
        self.add_toolbar("Login")

        # Content
        content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(16))

        content.add_widget(MDLabel(
            text="TwitchDropsMiner",
            font_style="H4",
            halign="center",
            size_hint_y=None,
            height=dp(50)
        ))

        content.add_widget(MDLabel(
            text="Enter your Twitch OAuth token to login",
            halign="center",
            size_hint_y=None,
            height=dp(40)
        ))

        self.token_field = MDTextField(
            hint_text="OAuth Token",
            helper_text="Get token from: https://twitchtokengenerator.com/",
            helper_text_mode="persistent",
            password=True
        )
        content.add_widget(self.token_field)

        login_btn = MDRaisedButton(
            text="Login",
            size_hint_y=None,
            height=dp(50),
            on_release=self.do_login
        )
        content.add_widget(login_btn)

        content.add_widget(MDLabel(
            text="How to get OAuth token:\n"
                 "1. Visit twitchtokengenerator.com\n"
                 "2. Select 'Custom Scope Token'\n"
                 "3. No scopes needed, just generate\n"
                 "4. Copy the token and paste here",
            size_hint_y=None,
            height=dp(120)
        ))

        self.layout.add_widget(content)

    def do_login(self, *args):
        """Perform login."""
        token = self.token_field.text.strip()
        if token:
            self.app.login(token)


class InventoryScreen(BaseScreen):
    """Inventory screen showing campaigns and drops."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Toolbar
        toolbar = self.add_toolbar("Inventory")
        toolbar.left_action_items = [["arrow-left", lambda x: self.app.screen_manager.switch_to(self.app.screen_manager.get_screen('home'))]]

        # Content
        scroll = ScrollView()
        self.list_view = MDList()
        scroll.add_widget(self.list_view)

        self.layout.add_widget(scroll)

    def update_inventory(self, inventory: list):
        """Update inventory list."""
        self.list_view.clear_widgets()

        if not inventory:
            self.list_view.add_widget(OneLineListItem(text="No campaigns available"))
            return

        for campaign in inventory:
            item = ThreeLineListItem(
                text=f"{campaign.name}",
                secondary_text=f"{campaign.game.name}",
                tertiary_text=f"Progress: {campaign.claimed_drops}/{campaign.total_drops} drops ({campaign.progress:.0%})"
            )
            self.list_view.add_widget(item)


class ChannelsScreen(BaseScreen):
    """Channels screen."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Toolbar
        toolbar = self.add_toolbar("Channels")
        toolbar.left_action_items = [["arrow-left", lambda x: self.app.screen_manager.switch_to(self.app.screen_manager.get_screen('home'))]]

        # Content
        scroll = ScrollView()
        self.list_view = MDList()
        scroll.add_widget(self.list_view)

        self.layout.add_widget(scroll)

        # Placeholder
        self.list_view.add_widget(OneLineListItem(text="No channels loaded"))


class SettingsScreen(BaseScreen):
    """Settings screen."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Toolbar
        toolbar = self.add_toolbar("Settings")
        toolbar.left_action_items = [["arrow-left", lambda x: self.app.screen_manager.switch_to(self.app.screen_manager.get_screen('home'))]]

        # Content
        scroll = ScrollView()
        content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(16), size_hint_y=None)
        content.bind(minimum_height=content.setter('height'))

        # Auto claim
        auto_claim_box = BoxLayout(size_hint_y=None, height=dp(50))
        auto_claim_box.add_widget(MDLabel(text="Auto Claim Drops"))
        auto_claim_switch = MDSwitch(active=self.app.settings.auto_claim)
        auto_claim_switch.bind(active=self.on_auto_claim_change)
        auto_claim_box.add_widget(auto_claim_switch)
        content.add_widget(auto_claim_box)

        # Notifications
        notif_box = BoxLayout(size_hint_y=None, height=dp(50))
        notif_box.add_widget(MDLabel(text="Notifications"))
        notif_switch = MDSwitch(active=self.app.settings.notifications_enabled)
        notif_switch.bind(active=self.on_notifications_change)
        notif_box.add_widget(notif_switch)
        content.add_widget(notif_box)

        # Logout button
        logout_btn = MDRaisedButton(
            text="Logout",
            size_hint_y=None,
            height=dp(50),
            on_release=lambda x: self.app.logout()
        )
        content.add_widget(logout_btn)

        scroll.add_widget(content)
        self.layout.add_widget(scroll)

    def on_auto_claim_change(self, instance, value):
        """Handle auto claim toggle."""
        self.app.settings.auto_claim = value
        self.app.settings.alter()
        self.app.settings.save()

    def on_notifications_change(self, instance, value):
        """Handle notifications toggle."""
        self.app.settings.notifications_enabled = value
        self.app.settings.alter()
        self.app.settings.save()


class LogsScreen(BaseScreen):
    """Logs screen."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Toolbar
        toolbar = self.add_toolbar("Logs")
        toolbar.left_action_items = [["arrow-left", lambda x: self.app.screen_manager.switch_to(self.app.screen_manager.get_screen('home'))]]
        toolbar.right_action_items = [["delete", self.clear_logs]]

        # Content
        scroll = ScrollView()
        self.list_view = MDList()
        scroll.add_widget(self.list_view)

        self.layout.add_widget(scroll)

    def add_log(self, message: str):
        """Add log message."""
        self.list_view.add_widget(OneLineListItem(text=message))

    def clear_logs(self, *args):
        """Clear all logs."""
        self.list_view.clear_widgets()
        self.app.logs.clear()
