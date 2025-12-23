import discord


def configdir_embed() -> tuple[discord.Embed, discord.File]:
    file = discord.File("data/avatar.png", filename="avatar.png")
    url = "https://wiki.ddnet.org/wiki/FAQ#Where_is_the_DDNet_config,_config_directory_or_save_directory?"

    embed = discord.Embed(
        description=(
            f"### [DDNet config directory:]({url})\n"
            "__**On Windows:**__\n"
            "Old: `%appdata%\\Teeworlds`\n"
            "New: `%appdata%\\DDNet`\n"
            "__**On Linux:**__\n"
            "Old: `~/.teeworlds`\n"
            "New: `~/.local/share/ddnet`\n"
            "__**On macOS:**__\n"
            "Old: `~/Library/Application Support/Teeworlds`\n"
            "New: `~/Library/Application Support/DDNet`"
        ),
        colour=discord.Colour.blurple(),
    )
    embed.set_thumbnail(url="attachment://avatar.png")
    return embed, file
