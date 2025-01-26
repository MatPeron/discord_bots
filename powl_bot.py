# Autore: Matteo Peron


#region IMPORTS

from datetime import datetime, timedelta
import os
import json
import discord
import logging
from logging.handlers import RotatingFileHandler
from discord import ui
from discord.ext import commands
from typing import List

#endregion

#region GLOBALS

POLL_STATUS = ["*APERTA*", "*CHIUSA*", "*ELIMINATA*"]
DEFAULT_OPTIONS = ["Indifferente", "Contrario a tutte le precedenti"]
MAX_N_POLL = 10-len(DEFAULT_OPTIONS) #maximum amount of poll options supported by Discord
MAX_DURATION = 7*24*3600 # maximum duration supported by Discord (7 days) 
MAX_SELECT = 10
EMBED_VALUE_LIMIT = 1024

token = #...
handler = RotatingFileHandler(
    filename='discord_powl_bot.log',
    encoding='utf-8',
    mode='a',
    maxBytes=5*1024**2,
    backupCount=3
)
logger = logging.getLogger("discord")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

#endregion

#region HISTORY

class PollHistoryEntry:

    def __init__(
        self,
        timestamp: str | datetime,
        duration: float | timedelta,
        quorum: int,
        majority: int,
        channel: int | discord.TextChannel,
        message: int| discord.Message,
        thread: int | discord.Thread,
        status: str
    ) -> None:
        
        self.timestamp = timestamp
        self.duration = duration
        self.quorum = quorum
        self.majority = majority
        self.channel = channel
        self.message = message
        self.thread = thread
        self.status = status
        

class PollHistory:

    def __init__(self, f: str) -> None:

        self.f = f
        self.database = self.load()

    def load(self):

        if not os.path.exists(self.f):
            with open(self.f, "w") as _:
                return {}
        else:
            with open(self.f, "r") as f:
                try:
                    return json.load(f)
                except json.decoder.JSONDecodeError:
                    return {}


    def dump(self):

        with open(self.f, "w") as f:
            json.dump(self.database, f, indent=4)
    
    def register(
        self,
        time: datetime,
        duration: timedelta,
        quorum: int,
        majority: int,
        channel: discord.TextChannel,
        message: discord.Message,
        thread: discord.Thread,
        status: str
    ):
        
        payload = {
            "timestamp": time.isoformat(),
            "duration": duration.total_seconds(),
            "quorum": quorum,
            "majority": majority,
            "channel": channel.id,
            "message": message.id,
            "thread": thread.id,
            "status": status
        }
        
        self.database[str(len(self.database)+1)] = payload
        self.dump()
        
    def retrieve(self, id):

        return PollHistoryEntry(**self.database[id])
    
    def update(self, id: str | None=None, status: int | None=None):

        for _, entry in self.database.items():
            if entry["status"]!=POLL_STATUS[0]:
                continue 

            start = datetime.fromisoformat(entry["timestamp"])
            duration = timedelta(seconds=entry["duration"])
            
            if datetime.now()>=start+duration:
                entry["status"] = POLL_STATUS[1] 
        
        if id is not None and status is not None:
            self.database[id]["status"] = POLL_STATUS[status]
            self.dump()

#endregion

#region SETTINGS

class PollSettings:

    def __init__(self,f: str) -> None:

        self.f = f
        self.channel = None
        self.majority = None
        self.quorum = None
        self.duration = None
        
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

class PollBot(commands.Bot):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.path = ".pollbot"
        self.fhistory = f"{self.path}/poll_history.json"
        self.fsettings = f"{self.path}/poll_settings.json"
        
        self.setup()

    def setup(self):

        if not os.path.exists(self.path):
            os.makedirs(self.path)

        self.history = PollHistory(self.fhistory)
        self.settings = PollSettings(self.fsettings)
    
    def reset(self):

        for f in os.listdir(self.path):
            os.remove(os.path.join(self.path, f))

        self.setup()
    
    async def on_ready(self):
        
        print("BOT READY")

        try:
            sync = await bot.tree.sync()
            print(f"SYNCHED {len(sync)} COMMAND(S)")
        except Exception as e:
            logger.exception(e)

    async def retrieve_entry_from_history(self, id: int):

        entry = self.history.retrieve(id)
        entry.channel = await self.fetch_channel(entry.channel)
        entry.message = await entry.channel.fetch_message(entry.message)
        entry.thread = await entry.message.fetch_thread()

        return entry
    
    async def retrieve_channel_from_settings(self):

        if self.settings.channel is not None:
            return await self.fetch_channel(self.settings.channel)
            

bot = PollBot(command_prefix="$", intents=intents)

#region command: AIUTO

@bot.tree.command(
    name="aiuto",
    description= \
        "Mostra informazioni sul bot e i comandi disponibili",
)
async def help(interaction: discord.Interaction):
    
    await interaction.response.send_message(
        "Usami per lanciare e gestire le votazioni in un server Discord. Posso tenere traccia"
        " di tutte le votazioni lanciate nel passato, gestirle, esportare i dati e impostare soglie"
        " di maggioranza e quorum per agevolare il processo di voto."+"\n"
        "\n"
        "Questa è la lista dei comandi che puoi invocare ovunque:"+"\n"
        "- `/aiuto`: mostra questo messaggio;"+"\n"
        "- `/impostazioni`: mostra un'interfaccia che permette di impostare alcuni parametri"
        " di default nelle votazioni, come il *canale* in cui lanciare le votazioni, soglie per la"
        " *maggioranza* e il *quorum*, e infine la *durata* delle votazioni (tutti questi parametri"
        " sono comunque modificabili nel momento in cui una votazione viene creata);"+"\n"
        "- `/votazione`: mostra un'interfaccia che permette di impostare tutti i parametri"
        " di una votazione, inclusi un *titolo* e delle *opzioni di voto* (a cui vegono aggiunte"
        " di default anche le opzioni \"indifferente\" e \"Contrario a tutte le precedenti\");"+"\n"
        "- `/gestisci`: mostra un'interfaccia che permette visualizzare e gestire tutte le votazioni"
        " lanciate con `/votazione`, per esempio chiudendo o cancellando la votazione, oppure"
        " esportando i voti su file, oppure ancora è possibile anche menzionare chi non ha ancora"
        " votato. **NOTA BENE: una volta chiusa, non è più possibile esportare i dati di una"
        " votazione**;"+"\n"
        "- `/reset`: elimina le impostazioni correnti e i dati dei tutte le votazioni, riportando"
        " il bot alla configurazione iniziale."+"\n"
        "\n"
        "Qui invece ci sono i comandi che possono essere invocati solo nel thread dedicato a una"
        " votazione:"+"\n"
        "- `/id`: permette di ottenere l'ID della votazione, utile per il comando `/gestisci` se"
        " esistono molte votazioni nello storico;"+"\n"
        "- `/pinga`: menziona chi non ha ancora votato;"+"\n"
        "- `/esporta`: esporta un file .csv contenente i dati della votazione.",
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

#region command: VOTAZIONE

class PollInterface(discord.Embed):

    def __init__(
            self,
            color: int | discord.Colour | None=discord.Color.random(),
            poll_title: str | None = None,
            poll_options: List[str] = [],
            poll_channel: discord.TextChannel | None = None,
            poll_majority: int | None = None,
            poll_quorum: int | None = None,
            poll_duration: float | None = None
        ):
        super().__init__(color=color)

        self.set_author(name="Impostazioni della votazione")

        display_title = self.format_title_to_display(poll_title)
        self.add_field(name="Titolo", value=display_title, inline=False)

        display_options = self.format_options_to_display(poll_options)
        self.add_field(name="Opzioni di voto", value=display_options, inline=False)

        display_channel = self.format_channel_to_display(poll_channel)
        self.add_field(name="Canale", value=display_channel, inline=True)

        display_majority = self.format_majority_to_display(poll_majority)
        self.add_field(name="Soglia di maggioranza", value=display_majority, inline=False)

        display_quorum = self.format_quorum_to_display(poll_quorum)
        self.add_field(name="Quorum", value=display_quorum, inline=True)

        display_duration = self.format_duration_to_display(poll_duration)
        self.add_field(name="Durata", value=display_duration, inline=False)

    def format_title_to_display(self, title):

        fmt = title if title is not None else "*non impostato*"

        if len(fmt)>EMBED_VALUE_LIMIT:
            fmt = title[:EMBED_VALUE_LIMIT-3]+"..."
        
        return fmt
        
    def format_options_to_display(self, options):

        fmt = "\n".join(
            [f"- {option}" for option in options+DEFAULT_OPTIONS]
        ) if options else "*non impostato (almeno 2)*"

        if len(fmt)>EMBED_VALUE_LIMIT:
            single_item_length = EMBED_VALUE_LIMIT//len(options)-6
            fmt = "\n".join([f"- {option[:single_item_length]}..." for option in options])

        return fmt
    
    def format_channel_to_display(self, channel):

        fmt = channel.mention if channel is not None else "*non impostato*"

        return fmt
    
    def format_majority_to_display(self, majority):
        
        try:
            if majority is None:
                fmt = "*non impostato*"
            elif int(majority)<0 or int(majority)>100:
                fmt = "*valore non valido*"
            else:
                fmt = f"{majority}%"
        except:
            fmt = "*valore non valido*"

        return fmt
    
    def format_quorum_to_display(self, quorum):
        
        try:
            if quorum is None:
                fmt = "*non impostato*"
            elif int(quorum)<0 or int(quorum)>100:
                fmt = "*valore non valido*"
            else:
                fmt = f"{quorum}%"
        except:
            fmt = "*valore non valido*"

        return fmt
    
    def format_duration_to_display(self, duration):
        
        try:
            if duration is None:
                fmt = "*non impostato*"
            elif float(duration)<0:
                fmt = "*valore non valido*"
            else:
                d, d_remainder = float(duration)//(3600*24), float(duration)%(3600*24)
                h, h_remainder = d_remainder//3600, d_remainder%3600
                m, m_remainder = h_remainder//60, h_remainder%60
                s = m_remainder//1
                fmt = f"{d} giorni, {h} ore, {m} minuti, {s} secondi"
        except:
            fmt = "*valore non valido*"

        return fmt
        

class PollInterfaceEditor(ui.View):

    def __init__(
        self, 
        *,
        timeout: float | None=None, 
        poll_channel: discord.TextChannel | None=None,
        poll_majority: int | None=None,
        poll_quorum: int | None=None,
        poll_duration: float | None=None
    ):
        super().__init__(timeout=timeout)

        self.is_cancelled = False
        
        self.poll_title = None
        self.poll_options = []
        self.poll_channel = poll_channel
        self.poll_majority = poll_majority
        self.poll_quorum = poll_quorum
        self.poll_duration = poll_duration

        self.select_channel = ui.ChannelSelect(placeholder="Seleziona canale", row=1)
        self.select_channel.callback = self.on_channel_select
        self.add_item(self.select_channel)

    def update_interface(self):

        interface = PollInterface(
            poll_title=self.poll_title,
            poll_options=self.poll_options,
            poll_channel=self.poll_channel,
            poll_majority=self.poll_majority,
            poll_quorum=self.poll_quorum,
            poll_duration=self.poll_duration
        )

        return interface
    
    async def on_channel_select(self, interaction: discord.Interaction):

        self.poll_channel = await bot.fetch_channel(self.select_channel.values[0].id)
        await interaction.response.defer()
        
        self.enable_send()
        await interaction.edit_original_response(embed=self.update_interface(), view=self)

    @ui.button(label="Modifica titolo", style=discord.ButtonStyle.primary, row=0)
    async def edit_title(self, interaction: discord.Interaction, button: ui.Button):

        modal = PollModal("Titolo", default=self.poll_title, is_title=True)
        await interaction.response.send_modal(modal)
        await modal.wait()

        self.poll_title = modal.value

        self.enable_send()
        await interaction.edit_original_response(embed=self.update_interface(), view=self)

    @ui.button(label="+ Opzione di voto", style=discord.ButtonStyle.primary, row=0)
    async def add_option(self, interaction: discord.Interaction, button: ui.Button):

        modal = PollModal("Opzione di voto", is_option=True)
        await interaction.response.send_modal(modal)
        await modal.wait()

        self.poll_options.append(modal.value)
        
        self.enable_send()
        await interaction.edit_original_response(embed=self.update_interface(), view=self)

    @ui.button(label="- Opzione di voto", style=discord.ButtonStyle.primary, row=0)
    async def remove_option(self, interaction: discord.Interaction, button: ui.Button):

        self.poll_options.pop()
        await interaction.response.defer()
        
        self.enable_send()
        await interaction.edit_original_response(embed=self.update_interface(), view=self)

    @ui.button(label="Modifica maggioranza", style=discord.ButtonStyle.primary, row=2)
    async def edit_majority(self, interaction: discord.Interaction, button: ui.Button):

        modal = PollModal("Maggioranza", default=self.poll_majority, is_majority=True)
        await interaction.response.send_modal(modal)
        await modal.wait()

        self.poll_majority = modal.value

        self.enable_send()
        await interaction.edit_original_response(embed=self.update_interface(), view=self)

    @ui.button(label="Modifica quorum", style=discord.ButtonStyle.primary, row=2)
    async def edit_quorum(self, interaction: discord.Interaction, button: ui.Button):

        modal = PollModal("Quorum", default=self.poll_quorum, is_quorum=True)
        await interaction.response.send_modal(modal)
        await modal.wait()

        self.poll_quorum = modal.value

        self.enable_send()
        await interaction.edit_original_response(embed=self.update_interface(), view=self)

    @ui.button(label="Modifica durata", style=discord.ButtonStyle.primary, row=2)
    async def edit_duration(self, interaction: discord.Interaction, button: ui.Button):

        modal = PollModal("Durata", default=self.poll_duration, is_duration=True)
        await interaction.response.send_modal(modal)
        await modal.wait()

        self.poll_duration = modal.value

        self.enable_send()
        await interaction.edit_original_response(embed=self.update_interface(), view=self)

    def enable_send(self):

        for child in self.children:
            if isinstance(child, ui.Button):
                if child.label=="Avvia votazione":
                    send_btn = child
                    send_btn.disabled = True

        try:
            if any([
                value is None for value in [
                    self.poll_channel,
                    self.poll_title,
                    self.poll_majority,
                    self.poll_quorum,
                    self.poll_duration
                ]
            ]) or not self.poll_options:
                pass
            elif int(self.poll_majority)<0 or int(self.poll_majority)>100:
                pass
            elif int(self.poll_quorum)<0 or int(self.poll_quorum)>100:
                pass
            elif int(self.poll_duration)<0 or int(self.poll_duration)>MAX_DURATION:
                pass
            elif len(self.poll_options)<2 or len(self.poll_options)>MAX_N_POLL:
                pass
            else:
                send_btn.disabled = False
        except Exception as e:
            logger.exception(e)
    
    @ui.button(label="Avvia votazione", disabled=True, style=discord.ButtonStyle.green, row=3)
    async def send(self, interaction: discord.Interaction, button: ui.Button):

        await interaction.response.defer()

        for child in self.children:
            child.disabled = True
        
        await interaction.edit_original_response(
            content="La votazione è ora avviata!",
            embed=self.update_interface(),
            view=self
        )

        self.poll_options.extend(DEFAULT_OPTIONS)
        self.poll_majority = int(self.poll_majority)
        self.poll_quorum = int(self.poll_quorum)
        self.poll_duration = timedelta(seconds=float(self.poll_duration))

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


class PollModal(ui.Modal):

    def __init__(
            self,
            title: str,
            default: str | None=None,
            is_title: bool=False,
            is_option: bool=False,
            is_majority: bool=False,
            is_quorum: bool=False,
            is_duration: bool=False
        ):
        super().__init__(title=title)

        if is_title:
            self.add_item(
                ui.TextInput(
                    label="Formula un titolo per la votazione",
                    default=default,
                    required=True,
                    style=discord.TextStyle.long
                )
            )
        
        if is_option:
            self.add_item(
                ui.TextInput(
                    label="Formula un'opzione di voto",
                    default=default,
                    required=True,
                    style=discord.TextStyle.long
                )
            )

        if is_majority:
            self.add_item(
                ui.TextInput(
                    label="Digita una soglia di maggioranza (da 0 a 100)",
                    default=default,
                    required=True,
                    style=discord.TextStyle.short
                )
            )

        if is_quorum:
            self.add_item(
                ui.TextInput(
                    label="Digita una soglia per il quorum (da 0 a 100)",
                    default=default,
                    required=True,
                    style=discord.TextStyle.short
                )
            )

        if is_duration:
            self.add_item(
                ui.TextInput(
                    label="Digita una durata (secondi, max 1 settimana)",
                    default=default,
                    required=True,
                    style=discord.TextStyle.short
                )
            )

    async def on_submit(self, interaction: discord.Interaction):

        self.value = self.children[0].value

        await interaction.response.defer()


@bot.tree.command(
    name="votazione",
    description="Crea una nuova votazione"
)
@commands.has_permissions(administrator=True)
async def make_poll(interaction: discord.Interaction):

    poll_channel = await bot.retrieve_channel_from_settings()
    poll_majority = bot.settings.majority
    poll_quorum = bot.settings.quorum
    poll_duration = bot.settings.duration
        
    interface = PollInterface(
        poll_channel=poll_channel,
        poll_majority=poll_majority,
        poll_quorum=poll_quorum,
        poll_duration=poll_duration
    )
    editor = PollInterfaceEditor(
        poll_channel=poll_channel,
        poll_majority=poll_majority,
        poll_quorum=poll_quorum,
        poll_duration=poll_duration
    )

    await interaction.response.send_message(embed=interface, view=editor, ephemeral=True)
    await editor.wait()

    if editor.is_cancelled:
        return
    
    poll = discord.Poll(
        question=editor.poll_title,
        duration=editor.poll_duration
    )
    for option in editor.poll_options:
        poll.add_answer(text=option)

    message = await editor.poll_channel.send(
        content=f"@everyone, {interaction.user.mention} ha appena lancianto una votazione, venghino!",
        poll=poll
    )

    thread = await editor.poll_channel.create_thread(
        name=f"{editor.poll_title} - DISCUSSIONE",
        message=message
    )
    await thread.send(
        content=f"@everyone, questo è il thread ufficiale per discutere la votazione."
    )

    bot.history.register(
        time=datetime.now(),
        duration=editor.poll_duration,
        quorum=editor.poll_quorum,
        majority=editor.poll_majority,
        channel=editor.poll_channel,
        message=message,
        thread=thread,
        status=POLL_STATUS[0]
    )

    logger.info("New poll registered.")

@make_poll.error
async def make_poll_error(interaction: discord.Interaction, error: Exception):

    logger.exception(error)

    await interaction.response.send_message(
        "Uh oh! Qualcosa è andato storto! Controlla i file di log per maggiori informazioni",
        ephemeral=True
    )

#endregion

#region command: GESTISCI

class PollHistoryInterface(discord.Embed):

    def __init__(
            self,
            start: int=0,
            stop: int=MAX_SELECT,
            color: int | discord.Colour | None=discord.Color.random()
        ):
        super().__init__(color=color)

        self.set_author(name="Storico votazioni")
        self.format_history(start, stop)

    async def ainit(
        self,
        id: str | None=None
    ):
        self.clear_fields()
        self.set_author(name="Storico votazioni")
        await self.format_entry(id)
    
    def format_history(self, start, stop):
        
        fmt = ""
        
        i = 0
        for id, entry in bot.history.database.items():
            if i>=start and i<stop:
                fmt += f"Votazione n.{id}: {entry['status']}"+"\n"
            elif i==stop:
                break

            i += 1

        self.add_field(name="Tutte le votazioni", value=fmt, inline=False)

    async def format_entry(self, id):

        poll_entry = await bot.retrieve_entry_from_history(id)
        users = [user.id for user in bot.get_all_members() if not user.bot]

        if poll_entry.status==POLL_STATUS[2]:
            self.add_field(name=f"Votazione n.{id}", value="**Votazione eliminata**", inline=False)
        else:
            display_header = self.format_header_to_display(poll_entry)
            self.add_field(name=f"Votazione n.{id}", value=display_header, inline=False)

            display_title = self.format_title_to_display(poll_entry)
            self.add_field(name=f"Titolo", value=display_title, inline=False)

            display_options = self.format_options_to_display(poll_entry, users)
            self.add_field(name=f"Opzioni di voto", value=display_options, inline=False)

            display_non_voters = await self.format_non_voters_to_display(poll_entry, users)
            self.add_field(name=f"Chi non ha votato?", value=display_non_voters, inline=False)

            display_channel = self.format_channel_to_display(poll_entry)
            self.add_field(name="Canale", value=display_channel, inline=True)

            display_majority = self.format_majority_to_display(poll_entry)
            self.add_field(name="Soglia di maggioranza", value=display_majority, inline=True)
            
            display_quorum = self.format_quorum_to_display(poll_entry, users)
            self.add_field(name="Quorum", value=display_quorum, inline=True)

    def format_header_to_display(self, poll_entry):
        
        fmt = f"[Vai alla votazione!]({poll_entry.message.jump_url})"+"\n"
        f"Creata in data: {poll_entry.timestamp}"+"\n"
        f"Scade il: {poll_entry.message.poll.expires_at.isoformat()}"

        return fmt
    
    def format_title_to_display(self, poll_entry):

        fmt = poll_entry.message.poll.question

        if len(fmt)>EMBED_VALUE_LIMIT:
            fmt = fmt[:EMBED_VALUE_LIMIT-3]+"..."
        
        return fmt
    
    def format_options_to_display(self, poll_entry, users):

        options = []
        max_votes = 0
        for option in poll_entry.message.poll.answers:
            tmp = f"- [{option.vote_count} voti] {option.text}"

            if option.vote_count>poll_entry.majority/100*poll_entry.message.poll.total_votes:
                tmp += " **(maggioranza raggiunta)**"

            if option.vote_count>max_votes:
                options = [tmp]+options
                max_votes = option.vote_count
                continue
            
            options += [tmp]

        fmt = "\n".join(options)

        if len(fmt)>EMBED_VALUE_LIMIT:
            single_item_length = EMBED_VALUE_LIMIT//len(options)-6
            fmt = "\n".join([f"- {option[:single_item_length]}..." for option in options])

        return fmt
    
    async def format_non_voters_to_display(self, poll_entry, users):

        non_voters, voters = [], []
        for option in poll_entry.message.poll.answers:
            async for voter in option.voters():
                voters.append(voter.id)

        for user in users:
            if user not in voters:
                non_voters.append(user)

        mentions = []
        for user in non_voters:
            tmp = await bot.fetch_user(user)
            mentions.append(tmp.mention)

        fmt = ", ".join(mentions)

        return fmt
    
    def format_channel_to_display(self, poll_entry):

        fmt = poll_entry.channel.mention

        return fmt
    
    def format_majority_to_display(self, poll_entry):

        fmt = f"{poll_entry.majority}%"

        return fmt
    
    def format_quorum_to_display(self, poll_entry, users):

        fmt = f"{poll_entry.quorum}%"
        if poll_entry.message.poll.total_votes>poll_entry.quorum/100*len(users):
            fmt += " **(quorum raggiunto)**"

        return fmt


class PollHistoryInterfaceEditor(ui.View):

    def __init__(
        self, 
        *,
        timeout: float | None=None
    ):
        super().__init__(timeout=timeout)

        self.start = 0
        self.sstop = MAX_SELECT

        self.refresh()

    def update_interface(self):

        interface = PollHistoryInterface(
            start=self.start,
            stop=self.sstop
        )

        return interface
    
    def refresh(self):

        for child in self.children:
            if isinstance(child, ui.Select):
                if child.placeholder=="Seleziona votazione":
                    self.remove_item(child)

            if isinstance(child, ui.Button):
                if child.label=="Precedente":
                    if self.start>0:
                        child.disabled = False
                    else:
                        child.disabled = True
                
                if child.label=="Successivo":
                    if self.sstop<len(bot.history.database):
                        child.disabled = False
                    else:
                        child.disabled = True
        
        self.make_select()
    
    def make_select(self):

        self.select_poll = ui.Select(placeholder="Seleziona votazione", row=1)
        self.select_poll.callback = self.on_poll_select

        i = 0
        for id in bot.history.database:
            if i>=self.start and i<self.sstop:
                self.select_poll.add_option(
                    label=f"Votazione n.{id}",
                    value=id
                )
            elif i==self.sstop:
                break

            i += 1

        self.add_item(self.select_poll)

    async def on_poll_select(self, interaction: discord.Interaction):

        await interaction.response.defer()

        poll_id = self.select_poll.values[0]
        
        interface = self.update_interface()
        await interface.ainit(poll_id)

        await interaction.edit_original_response(
            embed=interface,
            view=PollHistoryEntryInterfaceEditor(id=poll_id, stack=self),
            allowed_mentions=discord.AllowedMentions(users=False)
        )

    @ui.button(label="Precedente", style=discord.ButtonStyle.secondary, row=0)
    async def previous(self, interaction: discord.Interaction, button: ui.Button):

        await interaction.response.defer()

        self.start -= MAX_SELECT
        self.sstop -= MAX_SELECT
        self.refresh()
        
        await interaction.edit_original_response(embed=self.update_interface(), view=self)

    @ui.button(label="Successivo", style=discord.ButtonStyle.secondary, row=0)
    async def next(self, interaction: discord.Interaction, button: ui.Button):

        await interaction.response.defer()

        self.start += MAX_SELECT
        self.sstop += MAX_SELECT
        self.refresh()
        
        await interaction.edit_original_response(embed=self.update_interface(), view=self)

    @ui.button(label="Cancella", style=discord.ButtonStyle.red, row=2)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        
        await interaction.response.defer()

        await interaction.edit_original_response(
            content="Operazione annullata.",
            embed=None,
            view=None
        )

        self.stop()


class PollHistoryEntryInterfaceEditor(ui.View):

    def __init__(
        self, 
        *,
        timeout: float | None=None,
        id: str | None=None,
        stack: PollHistoryInterfaceEditor | None=None
    ):
        super().__init__(timeout=timeout)

        self.id = id
        self.stack = stack

        self.check_status()

    def check_status(self):

        poll_entry = bot.history.database[self.id]
        
        for child in self.children:
            if isinstance(child, ui.Button):
                if poll_entry["status"]==POLL_STATUS[1]:
                    if child.label=="Pinga non-votanti" or child.label=="Chiudi votazione":
                        child.disabled = True
                elif poll_entry["status"]==POLL_STATUS[2]:
                    child.disabled = True

    @ui.button(label="Pinga non-votanti", style=discord.ButtonStyle.primary, row=0)
    async def ping_non_voters(self, interaction: discord.Interaction, button: ui.Button):

        await interaction.response.defer()

        await _ping(self.id)

    @ui.button(label="Esporta risultati", style=discord.ButtonStyle.primary, row=0)
    async def export_poll(self, interaction: discord.Interaction, button: ui.Button):

        await interaction.response.defer()

        await _export(self.id)

    @ui.button(label="Chiudi votazione", style=discord.ButtonStyle.red, row=1)
    async def close_poll(self, interaction: discord.Interaction, button: ui.Button):

        await interaction.response.defer()
        
        poll_entry = await bot.retrieve_entry_from_history(self.id)
        await poll_entry.message.poll.end()
        message = await poll_entry.thread.send(content="La votazione è stata terminata.")
        await message.pin()

        bot.history.update(id=self.id, status=1)

        await interaction.edit_original_response(
            embed=self.stack.update_interface(),
            view=self.stack
        )

    @ui.button(label="Elimina votazione", style=discord.ButtonStyle.red, row=1)
    async def delete_poll(self, interaction: discord.Interaction, button: ui.Button):

        await interaction.response.defer()
        
        poll_entry = await bot.retrieve_entry_from_history(self.id)
        await poll_entry.thread.delete()
        await poll_entry.message.delete()

        bot.history.update(id=self.id, status=2)

        await interaction.edit_original_response(
            embed=self.stack.update_interface(),
            view=self.stack
        )

    @ui.button(label="Indietro", style=discord.ButtonStyle.secondary, row=2)
    async def back(self, interaction: discord.Interaction, button: ui.Button):

        await interaction.response.defer()
        
        await interaction.edit_original_response(
            embed=self.stack.update_interface(),
            view=self.stack
        )


@bot.tree.command(
    name="gestisci",
    description= \
        "Permette di gestire le singole votazioni.",
)
@commands.has_permissions(administrator=True)
async def manage_polls(interaction: discord.Interaction):
    
    if len(bot.history.database)==0:
        await interaction.response.send_message(
            "Non ci sono votazioni da gestire!",
            ephemeral=True
        )

        return

    bot.history.update()
    
    interface = PollHistoryInterface()
    editor = PollHistoryInterfaceEditor()

    await interaction.response.send_message(embed=interface, view=editor, ephemeral=True)
    await editor.wait()

    bot.history.dump()
    
@manage_polls.error
async def manage_polls_error(interaction: discord.Interaction, error: Exception):

    logger.exception(error)

    await interaction.response.send_message(
        "Uh oh! Qualcosa è andato storto! Controlla i file di log per maggiori informazioni",
        ephemeral=True
    )

#endregion

#region command: IMPOSTAZIONI
            
class PollSettingsInterface(discord.Embed):

    def __init__(
            self,
            color: int | discord.Colour | None=discord.Color.random(),
            poll_channel: discord.TextChannel | None = None,
            poll_majority: int | None = None,
            poll_quorum: int | None = None,
            poll_duration: float | None = None
        ):
        super().__init__(color=color)

        self.set_author(name="Impostazioni generali di default")

        display_channel = self.format_channel_to_display(poll_channel)
        self.add_field(name="Canale", value=display_channel, inline=False)

        display_majority = self.format_majority_to_display(poll_majority)
        self.add_field(name="Soglia di maggioranza", value=display_majority, inline=False)

        display_quorum = self.format_quorum_to_display(poll_quorum)
        self.add_field(name="Quorum", value=display_quorum, inline=False)

        display_duration = self.format_duration_to_display(poll_duration)
        self.add_field(name="Durata", value=display_duration, inline=False)
    
    def format_channel_to_display(self, channel):

        fmt = channel.mention if channel is not None else "*non impostato*"

        return fmt
    
    def format_majority_to_display(self, majority):
        
        try:
            if majority is None:
                fmt = "*non impostato*"
            elif int(majority)<0 or int(majority)>100:
                fmt = "*valore non valido*"
            else:
                fmt = f"{majority}%"
        except:
            fmt = "*valore non valido*"

        return fmt
    
    def format_quorum_to_display(self, quorum):
        
        try:
            if quorum is None:
                fmt = "*non impostato*"
            elif int(quorum)<0 or int(quorum)>100:
                fmt = "*valore non valido*"
            else:
                fmt = f"{quorum}%"
        except:
            fmt = "*valore non valido*"

        return fmt
    
    def format_duration_to_display(self, duration):
        
        try:
            if duration is None:
                fmt = "*non impostato*"
            elif float(duration)<0:
                fmt = "*valore non valido*"
            else:
                duration = float(duration)
                d, d_remainder = duration//(3600*24), duration%(3600*24)
                h, h_remainder = d_remainder//3600, d_remainder%3600
                m, m_remainder = h_remainder//60, h_remainder%60
                s = m_remainder//1
                fmt = f"{d:.0f} giorni, {h:.0f} ore, {m:.0f} minuti, {s:.0f} secondi"
        except:
            fmt = "*valore non valido*"

        return fmt
        

class PollSettingsInterfaceEditor(ui.View):

    def __init__(
        self, 
        *,
        timeout: float | None=None, 
        poll_channel: discord.TextChannel | None=None,
        poll_majority: int | None=None,
        poll_quorum: int | None=None,
        poll_duration: float | None=None
    ):
        super().__init__(timeout=timeout)

        self.is_cancelled = False

        self.poll_channel = poll_channel
        self.poll_majority = poll_majority
        self.poll_quorum = poll_quorum
        self.poll_duration = poll_duration

        self.select_channel = ui.ChannelSelect(placeholder="Seleziona canale", row=0)
        self.select_channel.callback = self.on_channel_select
        self.add_item(self.select_channel)

    def update_interface(self):

        interface = PollSettingsInterface(
            poll_channel=self.poll_channel,
            poll_majority=self.poll_majority,
            poll_quorum=self.poll_quorum,
            poll_duration=self.poll_duration
        )

        return interface
    
    async def on_channel_select(self, interaction: discord.Interaction):

        self.poll_channel = await bot.fetch_channel(self.select_channel.values[0].id)
        await interaction.response.defer()
        
        self.enable_send()
        await interaction.edit_original_response(embed=self.update_interface(), view=self)

    @ui.button(label="Modifica maggioranza", style=discord.ButtonStyle.primary, row=1)
    async def edit_majority(self, interaction: discord.Interaction, button: ui.Button):

        modal = PollModal("Maggioranza", default=self.poll_majority, is_majority=True)
        await interaction.response.send_modal(modal)
        await modal.wait()

        self.poll_majority = modal.value

        self.enable_send()
        await interaction.edit_original_response(embed=self.update_interface(), view=self)

    @ui.button(label="Modifica quorum", style=discord.ButtonStyle.primary, row=1)
    async def edit_quorum(self, interaction: discord.Interaction, button: ui.Button):

        modal = PollModal("Quorum", default=self.poll_quorum, is_quorum=True)
        await interaction.response.send_modal(modal)
        await modal.wait()

        self.poll_quorum = modal.value

        self.enable_send()
        await interaction.edit_original_response(embed=self.update_interface(), view=self)

    @ui.button(label="Modifica durata", style=discord.ButtonStyle.primary, row=1)
    async def edit_duration(self, interaction: discord.Interaction, button: ui.Button):

        modal = PollModal("Durata", default=self.poll_duration, is_duration=True)
        await interaction.response.send_modal(modal)
        await modal.wait()

        self.poll_duration = modal.value

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
                    self.poll_channel,
                    self.poll_majority,
                    self.poll_quorum,
                    self.poll_duration
                ]
            ]):
                pass
            elif int(self.poll_majority)<0 or int(self.poll_majority)>100:
                pass
            elif int(self.poll_quorum)<0 or int(self.poll_quorum)>100:
                pass
            elif float(self.poll_duration)<0 or float(self.poll_duration)>MAX_DURATION:
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

        self.poll_channel = self.poll_channel.id
        self.poll_majority = int(self.poll_majority)
        self.poll_quorum = int(self.poll_quorum)
        self.poll_duration = float(self.poll_duration)

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


@bot.tree.command(
    name="impostazioni",
    description= \
        "Mostra/modifica le impostazioni per le votazioni."
)
@commands.has_permissions(administrator=True)
async def make_settings(interaction: discord.Interaction):
    
    poll_channel = await bot.retrieve_channel_from_settings()
    poll_majority = bot.settings.majority
    poll_quorum = bot.settings.quorum
    poll_duration = bot.settings.duration
        
    interface = PollSettingsInterface(
        poll_channel=poll_channel,
        poll_majority=poll_majority,
        poll_quorum=poll_quorum,
        poll_duration=poll_duration
    )
    editor = PollSettingsInterfaceEditor(
        poll_channel=poll_channel,
        poll_majority=poll_majority,
        poll_quorum=poll_quorum,
        poll_duration=poll_duration
    )

    await interaction.response.send_message(embed=interface, view=editor, ephemeral=True)
    await editor.wait()

    if editor.is_cancelled:
        return
    
    bot.settings.channel = editor.poll_channel
    bot.settings.majority = editor.poll_majority
    bot.settings.quorum = editor.poll_quorum
    bot.settings.duration = editor.poll_duration
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

#region command: ID

@bot.tree.command(
    name="id",
    description= \
        "Da usare nel thread di discussione: "
        "restituisce l'ID della votazione",
)
@commands.has_permissions(administrator=True)
async def get_poll_id(interaction: discord.Interaction):
    
    for id, entry in bot.history.database.items():
        if entry["thread"]==interaction.channel.id:
            await interaction.response.send_message(
                f"L'ID della votazione corrente è: {id}",
                ephemeral=True
            )

            return

    await interaction.response.send_message(
        "Puoi usare questo comando solo nel thread dedicato ad una votazione!",
        ephemeral=True
    )

@get_poll_id.error
async def ping_remaining_error(interaction: discord.Interaction, error: Exception):

    logger.exception(error)

    await interaction.response.send_message(
        "Uh oh! Qualcosa è andato storto! Controlla i file di log per maggiori informazioni",
        ephemeral=True
    )

#endregion

#region command: PINGA

async def _ping(id: str):

    poll_entry = await bot.retrieve_entry_from_history(id)
    users = [user.id for user in bot.get_all_members() if not user.bot]

    non_voters, voters = [], []
    for option in poll_entry.message.poll.answers:
        async for voter in option.voters():
            voters.append(voter.id)

    for user in users:
        if user not in voters:
            non_voters.append(user)

    mentions = []
    for user in non_voters:
        tmp = await bot.fetch_user(user)
        mentions.append(tmp.mention)

    content = ", ".join(mentions)+" è stato richiesto il vostro voto!"
    await poll_entry.thread.send(content=content)

@bot.tree.command(
    name="pinga",
    description= \
        "Da usare nel thread di discussione: "
        "richiama gli utenti che non hanno ancora votato",
)
@commands.has_permissions(administrator=True)
async def ping_remaining(interaction: discord.Interaction):
    
    for id, entry in bot.history.database.items():
        if entry["thread"]==interaction.channel.id:
            if entry["status"]==POLL_STATUS[0]:
                await _ping(id)

                return
    
    await interaction.response.send_message(
        "Puoi usare questo comando solo nel thread dedicato ad una votazione aperta!",
        ephemeral=True
    )

@ping_remaining.error
async def ping_remaining_error(interaction: discord.Interaction, error: Exception):

    logger.exception(error)

    await interaction.response.send_message(
        "Uh oh! Qualcosa è andato storto! Controlla i file di log per maggiori informazioni",
        ephemeral=True
    )

#endregion

#region command: ESPORTA
    
async def _export(id):
    
    poll_entry = await bot.retrieve_entry_from_history(id)
    users = [user.id for user in bot.get_all_members() if not user.bot]

    filename = f"{bot.path}/poll_{id}_{poll_entry.message.poll.question.replace(' ', '-')}.csv"
    with open(filename, "w") as f:
        f.write("\"OPZIONE\",\"VOTI\",\"MAGGIORANZA\",\"QUORUM\""+"\n")
        for option in poll_entry.message.poll.answers:
            if option.vote_count>poll_entry.majority/100*poll_entry.message.poll.total_votes:
                f.write(f"\"{option.text}\",\"{option.vote_count}\",\"SI\",\"\""+"\n")
            else:
                f.write(f"\"{option.text}\",\"{option.vote_count}\",\"NO\",\"\""+"\n")
            
        f.write("\"\",\"\",\"\",\"\""+"\n")
        
        if poll_entry.message.poll.total_votes>poll_entry.quorum/100*len(users):
            quorum = "SI"
        else:
            quorum = "NO"
        
        f.write(
            f"\"HANNO VOTATO\",\"{poll_entry.message.poll.total_votes}\","
            f"\"su {len(users)}\",\"{quorum}\""+"\n"
        )

    message = await poll_entry.thread.send(
        content=f"La votazione è stata esportata su file!",
        file=discord.File(filename)
    )

    await message.pin()

@bot.tree.command(
    name="esporta",
    description= \
        "Da usare nel thread di discussione: "
        "esporta i dati di voto su file .csv",
)
@commands.has_permissions(administrator=True)
async def export_poll(interaction: discord.Interaction):
    
    for id, entry in bot.history.database.items():
        if entry["thread"]==interaction.channel.id:
            await _export(id)

            return
    
    await interaction.response.send_message(
        "Puoi usare questo comando solo nel thread dedicato ad una votazione aperta!",
        ephemeral=True
    )

@export_poll.error
async def export_poll_error(interaction: discord.Interaction, error: Exception):

    logger.exception(error)

    await interaction.response.send_message(
        "Uh oh! Qualcosa è andato storto! Controlla i file di log per maggiori informazioni",
        ephemeral=True
    )

#endregion

bot.run(
    token,
    log_handler=handler,
    log_level=logging.DEBUG
)
