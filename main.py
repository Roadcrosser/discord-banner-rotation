import discord
import random
import datetime
import os
import yaml
import asyncio
import re
from io import BytesIO

bot = discord.Client()

with open("config.yaml") as fl:
    config = yaml.load(fl, Loader=yaml.FullLoader)

bot.start_timestamp = 0
bot.done_banners = set()
bot.banner_queue = []
bot.current_banner = None

banners_fp = config["FILEPATH"]

if not banners_fp.endswith("/"):
    banners_fp += "/"


@bot.event
async def on_ready():
    log("Running...")

    if not bot.start_timestamp:
        bot.start_timestamp = datetime.datetime.utcnow()

        reload_banners()
        bot.loop.create_task(guild_banner_loop())


@bot.event
async def on_message(message):

    if (
        message.author.bot
        or not message.content
        or not message.channel.permissions_for(message.guild.me).send_messages
    ):
        return

    if re.match(
        "^((what|which) banner is this|what( is|'?s) this banner)\??$",
        message.content.lower(),
    ):
        await display_banner_info(message)
    elif re.match("^who( is|'?s) this banner\??$", message.content.lower()):
        await message.channel.send("me")
    elif re.match("^why( is|'?s) this banner\??$", message.content.lower()):
        await message.channel.send("yeah")
    elif re.match("^where( is|'?s) this banner\??$", message.content.lower()):
        await message.channel.send("here")
    elif re.match("^when( is|'?s) this banner\??$", message.content.lower()):
        await message.channel.send("now")
    elif re.match("^how( is|'?s) this banner\??$", message.content.lower()):
        await message.channel.send("the banner is doing well")
    elif message.content.lower() == config.get("RELOAD_CMD") and (
        is_maintainer(message.author)
    ):
        await reload_cmd(message)
    elif (
        config.get("EVAL_CMD")
        and message.content.lower().startswith(config.get("EVAL_CMD"))
        and (is_maintainer(message.author))
    ):
        await evaluate(message)


def is_maintainer(member):
    return member.id == config.get("OWNER_ID") or config.get("MAINTAINER_ROLE") in [
        r.id for r in member.roles
    ]


def log(message):
    print(f"[{datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] {message}")


async def display_banner_info(message):
    done_length = len(bot.done_banners)
    queue_length = len(bot.banner_queue)
    banner_total = done_length + queue_length
    msg = """{} banners in the pool. Current banner: `{}`
Percent exhausted: {:.2f}% ({}/{}, {} rotations until exhaustion)""".format(
        banner_total,
        bot.current_banner,
        (done_length / banner_total) * 100,
        done_length,
        banner_total,
        queue_length,
    )

    image = get_banner_data(bot.current_banner)

    if image:
        b = BytesIO()
        b.write(image)
        b.seek(0)
        image = discord.File(b, bot.current_banner.split("/")[-1])

    await message.channel.send(
        msg, file=image,
    )


async def guild_banner_loop():
    while True:

        interval = config["INTERVAL"]
        guild = bot.get_guild(config["GUILD_ID"])
        log("Updating banner...")
        if guild and guild.me.guild_permissions.manage_guild:
            new_banner = await update_banner(guild)
            log(
                f"Updated successfully to `{new_banner}`. Next update in {interval} seconds."
            )
            await update_banner_log(new_banner)
        else:
            interval = config.get("RETRY_INTERVAL", 5)
            log(f"Guild not found or no permissions. Retrying in {interval} seconds...")

        await asyncio.sleep(interval)


async def update_banner_log(new_banner):
    channel = bot.get_channel(config.get("LOG_CHANNEL_ID"))

    if not channel or not channel.permissions_for(channel.guild.me).send_messages:
        return

    await channel.send(f"The banner is now `{new_banner}`")


def get_banner_data(banner):
    fp = banners_fp + banner
    ret = None
    if os.path.isfile(fp):
        ret = open(banners_fp + banner, "rb").read()
    return ret


def reshuffle_queue():
    log("Banners exhausted. Reshuffling...")
    shuffle_into_banner_queue(bot.done_banners)
    bot.done_banners.clear()


async def update_banner(guild):

    image = None
    while not image:
        if not bot.banner_queue:
            reshuffle_queue()

        new_banner = bot.banner_queue.pop(0)

        image = get_banner_data(new_banner)

        if not image:
            log(f"Banner `{new_banner}` not found. Skipping...")
            continue

        await guild.edit(banner=image)

        bot.current_banner = new_banner
        bot.done_banners.add(new_banner)

    return new_banner


async def reload_cmd(message):
    new_banner_count, removed_banner_count = reload_banners()
    await message.channel.send(
        f"Banners reloaded:\n`{new_banner_count}` new banners added.\n`{removed_banner_count}` banners removed."
    )


def reload_banners():
    curr_banners = set(bot.banner_queue)
    seen_banners = set()

    new_banner_count = 0
    removed_banner_count = 0

    for wk in os.walk(banners_fp):
        for fl in wk[2]:
            if not fl.endswith(".png"):
                continue
            pdir = wk[0]
            if not pdir.endswith("/"):
                pdir += "/"

            fp = f"{pdir}{fl}"[len(banners_fp) :]

            seen_banners.add(fp)

            if fp in bot.done_banners:
                continue

            if not fp in curr_banners:
                curr_banners.add(fp)
                new_banner_count += 1

    for fl in bot.done_banners | curr_banners:
        if not fl in seen_banners:
            curr_banners.discard(fl)
            bot.done_banners.discard(fl)
            removed_banner_count += 1

    if new_banner_count > 0:
        shuffle_into_banner_queue(curr_banners)

    log(
        f"Banners reloaded. {new_banner_count} new banners added and {removed_banner_count} banners removed."
    )

    return (new_banner_count, removed_banner_count)


def shuffle_into_banner_queue(new_queue):
    bot.banner_queue = random.sample(new_queue, k=len(new_queue))


_ = None


async def evaluate(message):
    global _
    args = message.content[len(config.get("EVAL_CMD")) :].strip()

    if args.split(" ", 1)[0] == "await":
        try:
            _ = await eval(args.split(" ", 1)[1])
            await message.channel.send(_)
        except Exception as e:
            await message.channel.send("```\n" + str(e) + "\n```")
    else:
        try:
            _ = eval(args)
            await message.channel.send(_)
        except Exception as e:
            await message.channel.send("```\n" + str(e) + "\n```")
    return True


bot.run(config["TOKEN"])
