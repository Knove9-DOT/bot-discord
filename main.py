import os
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ================== CONFIGURE AQUI ==================
GUILD_ID = 1466211569766502453  # ID do servidor

CANAL_APROVACAO_ID = 1466211571167658039  # canal onde chegam os pedidos (Aprovar/Negar)
CANAL_LOG_ID = 1466211571167658043       # canal de logs (pode ser o mesmo ou outro)

# Quem pode aprovar/negar:
CARGOS_APROVADORES = [
    "Gerente Geral",
    "Gerente",
    "Gerente Vendas",
    "Gerente Rec",
]

# Cargos que o membro pode pedir no painel:
CARGOS_PERMITIDOS = [
    "Vapor",
    "Membro",
]

# Padrão do nickname após aprovar:
NICK_FORMAT = "[{cargo}] {nome} | {id}"
# ====================================================

intents = discord.Intents.default()
intents.members = True  # necessário para dar cargo / trocar nick

bot = commands.Bot(command_prefix="!", intents=intents)


def get_role_by_name(guild: discord.Guild, role_name: str) -> discord.Role | None:
    return discord.utils.get(guild.roles, name=role_name)


# ------------------ VIEW APROVAR / NEGAR ------------------
class AprovarNegarView(discord.ui.View):
    def __init__(self, user_id: int, cargo: str, nome_rp: str, id_rp: str):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.cargo = cargo
        self.nome_rp = nome_rp
        self.id_rp = id_rp

    def _tem_permissao(self, interaction: discord.Interaction) -> bool:
        guild = interaction.guild
        if not guild:
            return False
        membro = guild.get_member(interaction.user.id)
        if not membro:
            return False
        nomes = [r.name for r in membro.roles]
        return any(c in nomes for c in CARGOS_APROVADORES)

    @discord.ui.button(label="APROVAR", style=discord.ButtonStyle.success, custom_id="set_aprovar")
    async def aprovar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._tem_permissao(interaction):
            return await interaction.response.send_message("❌ Você não tem permissão para aprovar.", ephemeral=True)

        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("❌ Erro: guild não encontrada.", ephemeral=True)

        membro = guild.get_member(self.user_id)
        if not membro:
            return await interaction.response.send_message("❌ O membro não está mais no servidor.", ephemeral=True)

        role = get_role_by_name(guild, self.cargo)
        if not role:
            return await interaction.response.send_message(f"❌ Cargo **{self.cargo}** não existe.", ephemeral=True)

        # dar cargo
        try:
            await membro.add_roles(role, reason=f"Set aprovado por {interaction.user}")
        except discord.Forbidden:
            return await interaction.response.send_message(
                "❌ Não consegui dar o cargo (hierarquia/permissões do bot).", ephemeral=True
            )

        # trocar nick
        novo_nick = NICK_FORMAT.format(
            cargo=self.cargo.upper(),
            nome=self.nome_rp.strip(),
            id=str(self.id_rp).strip(),
        )

        nick_ok = True
        try:
            await membro.edit(nick=novo_nick, reason=f"Set aprovado por {interaction.user}")
        except discord.Forbidden:
            nick_ok = False

        # desativar botões
        for item in self.children:
            item.disabled = True

        await interaction.message.edit(
            content=f"✅ **APROVADO** por {interaction.user.mention}",
            view=self
        )

        if nick_ok:
            await interaction.response.send_message(f"✅ Aprovado! Nick: **{novo_nick}**", ephemeral=True)
        else:
            await interaction.response.send_message(
                "✅ Aprovado! (Não consegui alterar o nick — verifique 'Gerenciar Apelidos' e hierarquia.)",
                ephemeral=True
            )

        # log
        canal_log = guild.get_channel(CANAL_LOG_ID)
        if isinstance(canal_log, discord.TextChannel):
            await canal_log.send(
                f"✅ **SET APROVADO**\n"
                f"👤 Membro: {membro.mention} ({membro.id})\n"
                f"🎖 Cargo: **{role.name}**\n"
                f"📝 Nome/ID: **{self.nome_rp} | {self.id_rp}**\n"
                f"👮 Aprovador: {interaction.user.mention}\n"
                f"🏷 Nick: **{novo_nick}**"
            )

    @discord.ui.button(label="NEGAR", style=discord.ButtonStyle.danger, custom_id="set_negar")
    async def negar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._tem_permissao(interaction):
            return await interaction.response.send_message("❌ Você não tem permissão para negar.", ephemeral=True)

        for item in self.children:
            item.disabled = True

        await interaction.message.edit(
            content=f"❌ **NEGADO** por {interaction.user.mention}",
            view=self
        )
        await interaction.response.send_message("❌ Pedido negado.", ephemeral=True)

        guild = interaction.guild
        canal_log = guild.get_channel(CANAL_LOG_ID) if guild else None
        if isinstance(canal_log, discord.TextChannel):
            await canal_log.send(
                f"❌ **SET NEGADO**\n"
                f"👤 user_id: {self.user_id}\n"
                f"🎖 Cargo pedido: **{self.cargo}**\n"
                f"📝 Nome/ID: **{self.nome_rp} | {self.id_rp}**\n"
                f"👮 Negado por: {interaction.user.mention}"
            )


# ------------------ MODAL (FORMULÁRIO) ------------------
class SetModal(discord.ui.Modal, title="Solicitar Set"):
    def __init__(self, cargo_escolhido: str):
        super().__init__()
        self.cargo_escolhido = cargo_escolhido

        self.nome = discord.ui.TextInput(
            label="Seu nome (RP)",
            placeholder="Ex: João Silva",
            max_length=32
        )
        self.id_rp = discord.ui.TextInput(
            label="Seu ID (Cidade)",
            placeholder="Ex: 10293",
            max_length=10
        )

        self.add_item(self.nome)
        self.add_item(self.id_rp)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("❌ Isso só funciona no servidor.", ephemeral=True)

        # valida cargo permitido
        if self.cargo_escolhido not in CARGOS_PERMITIDOS:
            return await interaction.response.send_message("❌ Cargo inválido.", ephemeral=True)

        canal_aprov = guild.get_channel(CANAL_APROVACAO_ID)
        if not isinstance(canal_aprov, discord.TextChannel):
            return await interaction.response.send_message(
                "❌ Canal de aprovação não encontrado. Verifique CANAL_APROVACAO_ID.",
                ephemeral=True
            )

        embed = discord.Embed(title="📌 Pedido de SET", color=discord.Color.orange())
        embed.add_field(name="Membro", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
        embed.add_field(name="Cargo", value=self.cargo_escolhido, inline=True)
        embed.add_field(name="Nome", value=self.nome.value, inline=True)
        embed.add_field(name="ID", value=self.id_rp.value, inline=True)

        view = AprovarNegarView(
            user_id=interaction.user.id,
            cargo=self.cargo_escolhido,
            nome_rp=self.nome.value,
            id_rp=self.id_rp.value
        )

        await canal_aprov.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Pedido enviado para aprovação.", ephemeral=True)


# ------------------ VIEW DO PAINEL (MENU + BOTÃO) ------------------
class SetView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        options = [discord.SelectOption(label=n, value=n) for n in CARGOS_PERMITIDOS]

        self.select = discord.ui.Select(
            placeholder="Selecione seu cargo…",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="select_cargo"
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)

        self.botao = discord.ui.Button(
            label="SOLICITAR SET",
            style=discord.ButtonStyle.primary,
            custom_id="btn_solicitar_set"
        )
        self.botao.callback = self.botao_callback
        self.add_item(self.botao)

        self._cargo_por_user: dict[int, str] = {}

    async def select_callback(self, interaction: discord.Interaction):
        cargo = self.select.values[0]
        self._cargo_por_user[interaction.user.id] = cargo
        await interaction.response.send_message(
            f"✅ Cargo selecionado: **{cargo}**. Agora clique em **SOLICITAR SET**.",
            ephemeral=True
        )

    async def botao_callback(self, interaction: discord.Interaction):
        cargo = self._cargo_por_user.get(interaction.user.id)
        if not cargo:
            return await interaction.response.send_message(
                "⚠️ Primeiro selecione seu cargo no menu acima.",
                ephemeral=True
            )
        await interaction.response.send_modal(SetModal(cargo))


# ------------------ READY + SYNC ------------------
@bot.event
async def on_ready():
    # registrar views persistentes
    bot.add_view(SetView())
    bot.add_view(AprovarNegarView(0, "x", "x", "x"))

    # sync no servidor (rápido)
    synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"✅ Comandos sincronizados: {len(synced)}")
    print(f"✅ Logado como {bot.user}")


# ------------------ COMANDO DO PAINEL ------------------
@bot.tree.command(name="painelset", description="Envia o painel de solicitação de set")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def painelset(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    embed = discord.Embed(
        title="SOLICITAR SET",
        description="Selecione o cargo no menu e clique no botão para preencher sua solicitação.",
        color=discord.Color.blurple()
    )

    # manda o painel no canal
    await interaction.channel.send(embed=embed, view=SetView())
    await interaction.followup.send("✅ Painel enviado no canal.", ephemeral=True)


bot.run(TOKEN)