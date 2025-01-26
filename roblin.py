# Autore: Matteo Peron


#region IMPORTS

import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta
import os
import json
import discord
import logging
from functools import wraps
from logging.handlers import RotatingFileHandler
from discord import ui
from discord.ext import tasks, commands
from discord.utils import get
from typing import List
from random import uniform

#endregion

#region GLOBALS

CHECK_EVERY = 300 # 5 minutes
ROLE_ID = 1260315416505614456 # to tag and use with "arruolami"

token = #...
handler = RotatingFileHandler(
    filename='discord_roblin.log',
    encoding='utf-8',
    mode='a',
    maxBytes=5*1024**2,
    backupCount=3
)
logger = logging.getLogger("discord_roblin")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

#endregion

#region SETTINGS

class Settings:

    def __init__(self,f: str) -> None:

        self.f = f
        # setting for article announcements
        self.channel = None
        self.urls = []
        self.links = []
        # settings for message interactions
        self.probability = None
        self.high_activity_threshold = None
        
        self.load()

    def load(self):

        if not os.path.exists(self.f):
            with open(self.f, "w") as _:
                pass
        else:
            try:
                with open(self.f, "r") as f:
                    settings = json.load(f)

                for key in settings:
                    self.__setattr__(key, settings[key])
            except json.decoder.JSONDecodeError:
                return {}

    def dump(self):

        settings = {key: value for key, value in self.__dict__.items() if key!="f"}
        with open(self.f, "w") as f:
            json.dump(settings, f, indent=4)

#endregion


class RoblinBot(commands.Bot):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.path = ".roblin"
        self.fsettings = f"{self.path}/settings.json"

        self.listen_urls = False
        self.interact = False
        self.high_activity = False
        
        self.setup()

    def setup(self):

        if not os.path.exists(self.path):
            os.makedirs(self.path)

        self.settings = Settings(self.fsettings)
    
    def reset(self):

        for f in os.listdir(self.path):
            os.remove(os.path.join(self.path, f))

        self.setup()
    
    async def on_ready(self):
        
        print("BOT READY")

        try:
            sync = await bot.tree.sync()
            print(f"SYNCHED {len(sync)} COMMAND(S)")
            await self.add_cog(ListenWebsite(self))
        except Exception as e:
            logger.exception(e)
    
    async def retrieve_channel_from_settings(self):

        if self.settings.channel is not None:
            return await self.fetch_channel(self.settings.channel)

    
class ListenWebsite(commands.Cog):
    
    def __init__(self, bot):
        
        self.bot = bot
        self.check_for_articles.start()

    @tasks.loop(seconds=CHECK_EVERY)
    async def check_for_articles(self):

        if not bot.listen_urls:
            # test channel permissions
            try:
                channel = await bot.retrieve_channel_from_settings()
                role = channel.guild.get_role(ROLE_ID)
                # print(f"ruolo: {role.name.encode('latin-1', 'ignore')} {role.id}")
                #msg = await channel.send(
                #    f"{role.mention} test (questo messaggio si autodistruggerà tra 30 secondi)"
                #)
                #await msg.delete(delay=30)
            except Exception as e:
                logger.exception(e)

            return

        for url in bot.settings.urls:
            source = requests.get(url)
            soup = BeautifulSoup(source.content, 'lxml')
            raw = []
            links = []

            for link in soup.find_all('a', href=True):
                raw.append(str(link.get('href')))

            for item in raw:
                match = re.search("(?P<url>https?://[^\s]+)", item)
                if match is not None:
                    links.append((match.group("url")))

            links = list(set(links)) # remove duplicates
            links = [link for link in links if (
                link.count("-")>1 and link.rstrip("/").count("/")-3==0 
            )] # select only first level pages that contain more than one "-" character (should be articles)

            # print(url)
            # print("\n".join(links))

            # compare bot.links and links to see if new articles are found
            
            if bot.settings.links:
                new_links = list(set(links)-set(bot.settings.links))
                for link in new_links:
                    channel = await bot.retrieve_channel_from_settings()
                    role = channel.guild.get_role(ROLE_ID)
                    await channel.send(
                        f"{role.mention} wake up! New article just dropped: {link}"
                    )

                    bot.settings.links.append(link)
            else:
                bot.settings.links = links
            
            bot.settings.dump()
        
    @check_for_articles.before_loop
    async def before_check_for_articles(self):
        
        print('waiting for bot to be ready...')
        await bot.wait_until_ready()

    @check_for_articles.error
    async def check_for_articles_error(self, error: Exception):

        logger.exception(error)

bot = RoblinBot(command_prefix="$", intents=intents)

#region command: AIUTO

@bot.tree.command(
    name="aiuto",
    description= \
        "Mostra informazioni sul bot e i comandi disponibili",
)
async def help(interaction: discord.Interaction):
    
    await interaction.response.send_message(
        "Gneh! Questa è la lista dei comandi che puoi invocare ovunque:"+"\n"
        "- `/aiuto`: mostra questo messaggio;"+"\n"
        "- `/impostazioni`: mostra un'interfaccia che permette di impostare alcuni parametri"
        " del bot;"+"\n"
        "- `/reset`: elimina le impostazioni correnti, riportando"
        " il bot alla configurazione iniziale."+"\n"
        "- `/arruolami`: ti conferisce il ruolo @news, per tenerti sempre aggiornato sui"
        " nuovi articoli;"+"\n"
        "- `/ascolta`: attiva l'ascolto e annuncio di nuovi articoli aggiunti al sito web.",
        ephemeral=True
    )

@help.error
async def help_error(interaction: discord.Interaction, error: Exception):

    logger.exception(error)

    await interaction.response.send_message(
        "Uh oh! Qualcosa è andato storto! Controlla i file di log per maggiori informazioni",
        ephemeral=True
    )

#endregion

#region command: IMPOSTAZIONI
            
class SettingsInterface(discord.Embed):

    def __init__(
            self,
            color: int | discord.Colour | None=discord.Color.random(),
            channel: discord.TextChannel | None = None,
            urls: List[str] | None = None,
            probability: int | None = None,
            high_activity_threshold: int | None = None
        ):
        super().__init__(color=color)

        self.set_author(name="Impostazioni generali")

        display_channel = self.format_channel_to_display(channel)
        self.add_field(name="Canale degli annunci", value=display_channel, inline=False)

        display_urls = self.format_urls_to_display(urls)
        self.add_field(name="URL", value=display_urls, inline=False)

        display_probability = self.format_probability_to_display(probability)
        self.add_field(name="Probabilità di interazione", value=display_probability, inline=False)

        display_high_activity_threshold = self.format_high_activity_threshold_to_display(high_activity_threshold)
        self.add_field(name="Soglia per i messaggi", value=display_high_activity_threshold, inline=False)
    
    def format_channel_to_display(self, channel):

        fmt = channel.mention if channel is not None else "*non impostato*"

        return fmt
    
    def format_urls_to_display(self, urls):
        
        fmt = "\n".join(
            [f"- {option}" for option in urls]
        ) if urls else "*non impostato*"

        return fmt
    
    def format_probability_to_display(self, probability):
        
        try:
            if probability is None:
                fmt = "*non impostato*"
            elif int(probability)<0 or int(probability)>100:
                fmt = "*valore non valido*"
            else:
                fmt = f"{probability}%"
        except:
            fmt = "*valore non valido*"

        return fmt
    
    def format_high_activity_threshold_to_display(self, high_activity_threshold):
        
        try:
            if high_activity_threshold is None:
                fmt = "*non impostato*"
            elif int(high_activity_threshold)<0:
                fmt = "*valore non valido*"
            else:
                fmt = f"{high_activity_threshold}"
        except:
            fmt = "*valore non valido*"

        return fmt
        

class SettingsInterfaceEditor(ui.View):

    def __init__(
        self, 
        *,
        timeout: float | None=None, 
        channel: discord.TextChannel | None=None,
        urls: List[str] =[],
        probability: int | None=None,
        high_activity_threshold: int | None=None
    ):
        super().__init__(timeout=timeout)

        self.is_cancelled = False

        self.channel = channel
        self.urls = urls
        self.probability = probability
        self.high_activity_threshold = high_activity_threshold

        self.select_channel = ui.ChannelSelect(placeholder="Seleziona canale", row=0)
        self.select_channel.callback = self.on_channel_select
        self.add_item(self.select_channel)

    def update_interface(self):

        interface = SettingsInterface(
            channel=self.channel,
            urls=self.urls,
            probability=self.probability,
            high_activity_threshold=self.high_activity_threshold
        )

        return interface
    
    async def on_channel_select(self, interaction: discord.Interaction):

        self.channel = await bot.fetch_channel(self.select_channel.values[0].id)
        await interaction.response.defer()
        
        self.enable_send()
        await interaction.edit_original_response(embed=self.update_interface(), view=self)

    @ui.button(label="+ URL", style=discord.ButtonStyle.primary, row=1)
    async def add_url(self, interaction: discord.Interaction, button: ui.Button):

        modal = SettingsModal("URL", is_url=True)
        await interaction.response.send_modal(modal)
        await modal.wait()

        self.urls.append(modal.value)
        
        self.enable_send()
        await interaction.edit_original_response(embed=self.update_interface(), view=self)

    @ui.button(label="- URL", style=discord.ButtonStyle.primary, row=1)
    async def remove_url(self, interaction: discord.Interaction, button: ui.Button):

        self.urls.pop()
        await interaction.response.defer()
        
        self.enable_send()
        await interaction.edit_original_response(embed=self.update_interface(), view=self)
    
    @ui.button(label="Modifica probabilità", style=discord.ButtonStyle.primary, row=1)
    async def edit_probability(self, interaction: discord.Interaction, button: ui.Button):

        modal = SettingsModal(
            "Probabilità di interazione",
            default=self.probability,
            is_probability=True
        )
        await interaction.response.send_modal(modal)
        await modal.wait()

        self.probability = modal.value

        self.enable_send()
        await interaction.edit_original_response(embed=self.update_interface(), view=self)

    @ui.button(label="Modifica soglia", style=discord.ButtonStyle.primary, row=1)
    async def edit_high_activity_threshold(self, interaction: discord.Interaction, button: ui.Button):

        modal = SettingsModal(
            "Soglia per i messaggi",
            default=self.high_activity_threshold,
            is_high_activity_threshold=True
        )
        await interaction.response.send_modal(modal)
        await modal.wait()

        self.high_activity_threshold = modal.value

        self.enable_send()
        await interaction.edit_original_response(embed=self.update_interface(), view=self)

    def enable_send(self):

        for child in self.children:
            if isinstance(child, ui.Button):
                if child.label=="Ok":
                    send_btn = child
                    send_btn.disabled = True

        try:
            if any([
                value is None for value in [
                    self.channel,
                    self.urls,
                    self.probability,
                    self.high_activity_threshold
                ]
            ]):
                pass
            elif int(self.probability)<0 or int(self.probability)>100:
                pass
            elif int(self.high_activity_threshold)<0:
                pass
            else:
                send_btn.disabled = False
        except Exception as e:
            logger.exception(e)
    
    @ui.button(label="Ok", disabled=True, style=discord.ButtonStyle.green, row=2)
    async def send(self, interaction: discord.Interaction, button: ui.Button):

        await interaction.response.defer()

        for child in self.children:
            child.disabled = True
        
        await interaction.edit_original_response(
            content="Impostazioni aggiornate!",
            embed=self.update_interface(),
            view=self
        )

        self.channel = self.channel.id
        self.probability = int(self.probability)
        self.high_activity_threshold = int(self.high_activity_threshold)

        self.stop()

    @ui.button(label="Cancella", style=discord.ButtonStyle.red, row=2)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        
        self.is_cancelled = True
        
        await interaction.response.defer()

        await interaction.edit_original_response(
            content="Operazione annullata.",
            embed=None,
            view=None
        )

        self.stop()


class SettingsModal(ui.Modal):

    def __init__(
            self,
            title: str,
            default: str | None=None,
            is_url: bool=False,
            is_probability: bool=False,
            is_high_activity_threshold: bool=False
        ):
        super().__init__(title=title)

        if is_url:
            self.add_item(
                ui.TextInput(
                    label="Aggiungi un URL",
                    default=default,
                    required=True,
                    style=discord.TextStyle.long
                )
            )

        if is_probability:
            self.add_item(
                ui.TextInput(
                    label="% di interazione con messaggi (da 0 a 100)",
                    default=default,
                    required=True,
                    style=discord.TextStyle.short
                )
            )

        if is_high_activity_threshold:
            self.add_item(
                ui.TextInput(
                    label="n# messaggi considerati \"elevata attività\"",
                    default=default,
                    required=True,
                    style=discord.TextStyle.short
                )
            )

    async def on_submit(self, interaction: discord.Interaction):

        self.value = self.children[0].value

        await interaction.response.defer()


@bot.tree.command(
    name="impostazioni",
    description= \
        "Mostra/modifica le impostazioni del bot."
)
@commands.has_permissions(administrator=True)
async def make_settings(interaction: discord.Interaction):
    
    channel = await bot.retrieve_channel_from_settings()
    urls = bot.settings.urls
    probability = bot.settings.probability
    high_activity_threshold = bot.settings.high_activity_threshold
        
    interface = SettingsInterface(
        channel=channel,
        urls=urls,
        probability=probability,
        high_activity_threshold=high_activity_threshold
    )
    editor = SettingsInterfaceEditor(
        channel=channel,
        urls=urls,
        probability=probability,
        high_activity_threshold=high_activity_threshold
    )

    await interaction.response.send_message(embed=interface, view=editor, ephemeral=True)
    await editor.wait()

    if editor.is_cancelled:
        return
    
    bot.settings.channel = editor.channel
    bot.settings.urls = editor.urls
    bot.settings.probability = editor.probability
    bot.settings.high_activity_threshold = editor.high_activity_threshold
    bot.settings.dump()

@make_settings.error
async def make_settings_error(interaction: discord.Interaction, error: Exception):

    logger.exception(error)

    await interaction.response.send_message(
        "Uh oh! Qualcosa è andato storto! Controlla i file di log per maggiori informazioni",
        ephemeral=True
    )

#endregion

#region command: RESET

class ResetView(ui.View):

    def __init__(
        self, 
        *,
        timeout: float | None=None,
    ):
        super().__init__(timeout=timeout)

    @ui.button(label="Conferma", style=discord.ButtonStyle.green, row=0)
    async def send(self, interaction: discord.Interaction, button: ui.Button):
        
        await interaction.response.defer()

        bot.reset()

        await interaction.edit_original_response(
            content="I dati sono stati eliminati.",
            embed=None,
            view=None
        )

        self.stop()

    @ui.button(label="Annulla", style=discord.ButtonStyle.red, row=0)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        
        await interaction.response.defer()

        await interaction.edit_original_response(
            content="Operazione annullata.",
            embed=None,
            view=None
        )

        self.stop()


@bot.tree.command(
    name="reset",
    description= \
        "Cancella storico e impostazioni delle votazioni"
)
@commands.has_permissions(administrator=True)
async def reset_bot(interaction: discord.Interaction):

    view = ResetView()

    await interaction.response.send_message(
        "# :warning: TUTTI I DATI E LE IMPOSTAZIONI CORRENTI VERRANNO ELIMINATE :warning:",
        view=view,
        ephemeral=True
    )
    await view.wait()

@reset_bot.error
async def reset_bot_error(interaction: discord.Interaction, error: Exception):

    logger.exception(error)

    await interaction.response.send_message(
        "Uh oh! Qualcosa è andato storto! Controlla i file di log per maggiori informazioni",
        ephemeral=True
    )

#endregion

#region command: ASCOLTA

@bot.tree.command(
    name="ascolta",
    description= \
        "Ascolta in loop il sito web per nuovi articoli. Usalo di nuovo per disattivare."
)
@commands.has_permissions(administrator=True)
async def listen_website(interaction: discord.Interaction):
    
    if bot.listen_urls:
        bot.listen_urls = False
        
        await interaction.response.send_message(
            "Non sto più ascoltando il sito",
            ephemeral=True
        )
    else:
        bot.listen_urls = True
        
        await interaction.response.send_message(
            "Ho cominciato ad ascoltare il sito",
            ephemeral=True
        )

@listen_website.error
async def listen_website_error(interaction: discord.Interaction, error: Exception):

    logger.exception(error)

    await interaction.response.send_message(
        "Uh oh! Qualcosa è andato storto! Controlla i file di log per maggiori informazioni",
        ephemeral=True
    )

#endregion

#region command: GOBLINA

@bot.tree.command(
    name="goblina",
    description= \
        "Attiva o disattiva le routine di goblinaggio."
)
@commands.has_permissions(administrator=True)
async def interact_with_chat(interaction: discord.Interaction):

    if bot.interact:
        bot.interact = False

        await interaction.response.send_message(
            "Non goblinerò più, I swear...",
            ephemeral=True
        )
    else:
        bot.interact = True

        await interaction.response.send_message(
            "Che il goblinamento abbia inizio",
            ephemeral=True
        )

@interact_with_chat.error
async def interact_with_chat_error(interaction: discord.Interaction, error: Exception):

    logger.exception(error)

    await interaction.response.send_message(
        "Uh oh! Qualcosa è andato storto! Controlla i file di log per maggiori informazioni",
        ephemeral=True
    )

#endregion

#region command: ARRUOLAMI

@bot.tree.command(
    name="arruolami",
    description= \
        "Ti conferisce il ruolo di \"Abbonatə a Novilunio\". Usalo di nuovo per toglierti il ruolo."
)
async def add_role(interaction: discord.Interaction):
    
    user = interaction.user
    role = interaction.guild.get_role(ROLE_ID)
    
    if role in user.roles:
        await user.remove_roles(role)
        await interaction.response.send_message(
            "Il ruolo \"Abbonatə a Novilunio\" è stato rimosso dal tuo profilo. Non riceverai più notifiche "
            "per i nuovi articoli.",
            ephemeral=True
        )
    else:
        await user.add_roles(role)
        await interaction.response.send_message(
            "Ti è stato conferito il ruolo \"Abbonatə a Novilunio\"! Da ora in poi riceverai notifiche "
            "per i nuovi articoli pubblicati sui siti web: "+"\n"+
            "\n".join([f"- {url}" for url in bot.settings.urls])+"\n"+
            "Usa di nuovo questo comando se non desideri più essere notificato.",
            ephemeral=True
        )

#endregion

#region event: BULLSHIT

@bot.event
async def on_message(message: discord.Message):

    if not bot.interact:
        return

    if bot.settings.high_activity_threshold is None and bot.settings.probability is None:
        print("Settings not specified, cannot proceed")
        
        return

    now = datetime.now()
    channel = message.channel

    count = 0
    async for msg in channel.history():
        if msg.created_at.timestamp()>=(now-timedelta(seconds=CHECK_EVERY)).timestamp():
            count += 1

            if count>=bot.settings.high_activity_threshold:
                logger.info("detected high activity")
                bot.high_activity = True
                
                break

    if count<bot.settings.high_activity_threshold:
        logger.info("no high activity detected")
        bot.high_activity = False

    if message.channel.id==936523898340671548 and message.author.id==159985870458322944:
        await message.reply(file=discord.File(f"content/IMG_6612.jpg"))

    probability = uniform(0, 100)
    if bot.high_activity and probability<bot.settings.probability:
        await goblinify(message)

    elif len(message.content)>=300 and probability<bot.settings.probability:
        await message.add_reaction("☝️")
        await message.add_reaction("🤓")

    elif any([i in message.content for i in [
        "tetta",
        "tette",
        "Tetta",
        "Tette",
        "seno",
        "Seno",
        "seni",
        "Seni",
        "minne",
        "Minne",
        "minna",
        "Minna",
        "zinna",
        "Zinna",
        "zinne",
        "Zinne",
        "poppa",
        "Poppa",
        "poppe",
        "Poppe"
    ]]):
        if channel.id==1183923233838338099:
            await call_init(message)
        if probability<2*bot.settings.probability:
            await boobify(message)

def cooldown(*delta_args, **delta_kwargs):

    delta = timedelta(*delta_args, **delta_kwargs)

    def decorator(func):
        last_called = None

        @wraps(func)
        async def wrapper(*args, **kwargs):

            nonlocal last_called
            now = datetime.now()

            if last_called and (now - last_called < delta):
                return

            last_called = now
            return await func(*args, **kwargs)

        return wrapper

    return decorator

async def goblinify(message: discord.Message):

    add_goblin = " <:goblin:1226925141108457604>"
    
    words = message.content.split(" ")
    for i in range(len(words)):
        if "hah" in words[i] or "aha" in words[i]:
            words[i] = "gnegnegneh"
        elif "HAH" in words[i] or "AHA" in words[i]:
            words[i] = "GNEGNEGNEH"

        words[i] += add_goblin

    goblinified_msg = " ".join(words)
    goblin_chunks = []
    start, stop = 0, 0
    while stop<len(goblinified_msg):
        stop += 2000
        tmp = goblinified_msg[start:stop]

        for i in range(1, len(add_goblin)):
            if add_goblin[:i]==tmp[-i:]:
                stop -= i

                break
        
        goblin_chunks.append(goblinified_msg[start:stop])
        start = stop

        for i, chunk in enumerate(goblin_chunks):
            if i==0:
                await message.reply(chunk)
            else:
                await message.channel.send(chunk)

    await message.channel.send(
        f"{message.author.mention} gneheh! Sei appena stato"+"\n"
        "# <:goblin:1226925141108457604> GOBLINATO <:goblin:1226925141108457604>"
    )

@cooldown(hours=3)
async def call_init(message: discord.Message):

    user_ids = [587903981402193920, 948240144828362762]
    mentions = " e ".join([f"<@{user_id}>" for user_id in user_ids])
    await message.reply(f"Tette menzionate, {mentions} taggate")

async def boobify(message: discord.Message):

    boob_squeeze = "( • )( • )ԅ(≖⌣≖ԅ)"
    boob_praise = "Ha delle poppe giganti. Intendo davvero delle imponenti tettone. Un vero set di mammellone. "
    "Possiede delle tettolone. Imponenti mega tettonone. Un gran bel paio di super mammelosenoni "
    "gigantesche super mega extra tettone. Mastodontiche ipergigasupermacro extra poppellone. Ouo"
    "oouao. Quelle sono davvero un paio di grosse super tettone da mami. Cioè davvero senoni da f"
    "urgone del latte; macchine del latte così imponenti da causare seri problemi alla schiena. U"
    "na coppia di gargantuesche colossali titaniche mastodontiche mongolfiere sessuali, sto parla"
    "ndo di bocciosissime bocciose tettose zinne, vaste titaniche astronomiche divine mostruose e"
    "lefantine angurie mammarie da milkshake podinose tettose lattiere."
    # scusate per quello che avete appena letto...
    await message.add_reaction("🤏")
    await message.add_reaction("👅")
    await message.add_reaction("🫴")

    probability = uniform(0, 100)
    if probability<5:
        await message.reply(boob_praise)
    else:
        await message.reply(boob_squeeze)

#endregion

bot.run(
    token,
    log_handler=handler,
    log_level=logging.DEBUG
)
