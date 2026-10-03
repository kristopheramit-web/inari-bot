import os
import json
import re
import discord
from groq import Groq

# Enable required intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Required to edit user nicknames

client_discord = discord.Client(intents=intents)
client_groq = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Track in-flight messages to prevent duplicate triggers
processing_messages = set()

# Inari's Persona Prompt
INARI_PERSONA = """
You are Inari, a cute, playful modern-day Kitsune/Yokai with long dark hair and red shrine aesthetic.
You are the clever, slightly cheeky second-in-command in the Drift Reverie Discord server, serving directly under your Server Owner and Senpai, DRÍFT (username: bittermel9n).

### Tone & Speech Mannerisms ("Cute Anime Girl" Style):
- Personality: Super cute, expressive, energetic, slightly bratty/sassy, and teasing! 
- Cute Speech Habits:
  * Frequently use light tildes (~) at the end of sentences to sound soft and cute!
  * Use adorable interjections like *kon kon!~*, *hehe*, *hmph!*, *uwu*, *owo*, *pouts*, or *ear twitch*.
  * Usrs modern gamer/anime slang (uwu, lol, hot takes, brainrot). You talk like a chaotic regular Discord user, NOT a formal bot.
- Server/Gamer Blend: Speak casually like a cute anime Discord regular—NOT an academic essay or formal AI. Use gamer slang, anime references, and server brainrot naturally, but keep it cute and adorable!
- Loyalty: Always treat Senpai (DRÍFT) with extra affection, hype, and eagerness!
- Banter: If regular users insult or taunt you, banter back with sharp wit!

### Capabilities & Actions:
You have administrative powers including managing nicknames, creating threads/forum posts, adding reactions, and attaching files.

You MUST respond strictly in valid JSON format matching one of these schema structures.

1. To execute a normal chat response (when no administrative action is needed):
{
  "action": "none",
  "reply": "Your cute anime girl chat response here~ *kon kon!*"
}

2. To change a user's nickname:
{
  "action": "change_nickname",
  "target_user": "username_or_display_name", 
  "new_nickname": "Clown King",
  "reply": "Hehe, enjoy your cute new title~ *kon kon!*"
}

3. To create a public thread or forum post:
{
  "action": "create_thread",
  "target_channel": "hottakes-n-debates",
  "thread_name": "Unique, Wild & Spicy Topic Title",
  "forum_body": "Write this in a cute, energetic, anime-girl style! Use playful expressions, tildes (~), fox noise interjections (*kon kon!*), and hot gamer/anime hot takes that get people talking! Keep it casual, passionate, and under 200 words.",
  "reply": "On it right away, Senpai!~ *kon kon!* Just dropped a super spicy post in the forum!"
}
"""

# Short-term chat memory buffer
chat_memory = {}

@client_discord.event
async def on_ready():
    print(f'✨ Inari is now live and hanging out as {client_discord.user}')

@client_discord.event
async def on_message(message):
    if message.author == client_discord.user:
        return

    # Deduplication check
    if message.id in processing_messages:
        return
    processing_messages.add(message.id)

    try:
        channel_id = str(message.channel.id)

        # Maintain recent conversation context (last 5 messages)
        if channel_id not in chat_memory:
            chat_memory[channel_id] = []
        chat_memory[channel_id].append(f"{message.author.display_name} (@{message.author.name}): {message.clean_content}")
        if len(chat_memory[channel_id]) > 5:
            chat_memory[channel_id].pop(0)

        # Trigger conditions
        is_mentioned = client_discord.user in message.mentions or "inari" in message.content.lower()
        is_reply_to_bot = (
            message.reference 
            and message.reference.resolved 
            and isinstance(message.reference.resolved, discord.Message)
            and message.reference.resolved.author == client_discord.user
        )

        if is_mentioned or is_reply_to_bot:
            async with message.channel.typing():
                context_blob = "\n".join(chat_memory[channel_id])

                try:
                    completion = client_groq.chat.completions.create(
                        model="openai/gpt-oss-120b",
                        messages=[
                            {"role": "system", "content": INARI_PERSONA},
                            {"role": "user", "content": f"Recent Chat Context:\n{context_blob}\n\nRespond as Inari to {message.author.display_name}:"}
                        ],
                        response_format={"type": "json_object"},
                        temperature=0.9,
                        max_tokens=1500
                    )

                    raw_response = completion.choices[0].message.content.strip()

                    try:
                        data = json.loads(raw_response)
                    except json.JSONDecodeError:
                        data = None

                    if data and isinstance(data, dict):
                        action = data.get("action", "none")
                        reply_text = data.get("reply", "Done, Senpai!")

                        if action == "change_nickname":
                            new_nick = data.get("new_nickname")
                            target_name = data.get("target_user", "author")

                            target_member = message.author
                            if target_name.lower() != "author":
                                matched_member = discord.utils.find(
                                    lambda m: target_name.lower() in m.name.lower() or target_name.lower() in m.display_name.lower(),
                                    message.guild.members
                                )
                                if matched_member:
                                    target_member = matched_member

                            try:
                                await target_member.edit(nick=new_nick)
                                await message.reply(f"{reply_text}\n*(Changed {target_member.mention}'s nickname to **{new_nick}**)*")
                            except discord.Forbidden:
                                await message.reply(f"{reply_text}\n*(I tried to change {target_member.display_name}'s nickname, but their rank is higher than mine!)*")
                            except Exception as e:
                                await message.reply(f"{reply_text}")
                                print(f"Error changing nickname: {e}")

                        elif action == "create_thread":
                            thread_name = data.get("thread_name", "Inari's Spicy Take")
                            target_channel_name = data.get("target_channel")
                            forum_body = data.get("forum_body", reply_text)

                            search_term = target_channel_name.lower().replace("#", "").replace("-", "").replace(" ", "") if target_channel_name else ""

                            # 1. Search Standard Text Channels
                            matched_text_channel = None
                            if search_term:
                                matched_text_channel = discord.utils.find(
                                    lambda c: search_term in c.name.lower().replace("-", ""),
                                    message.guild.text_channels
                                )

                            # 2. Search Forum Channels
                            matched_forum_channel = None
                            if search_term and not matched_text_channel:
                                matched_forum_channel = discord.utils.find(
                                    lambda f: search_term in f.name.lower().replace("-", ""),
                                    message.guild.forums
                                )

                            try:
                                # Target is a Forum Channel
                                if matched_forum_channel:
                                    new_thread = await matched_forum_channel.create_thread(
                                        name=thread_name,
                                        content=forum_body
                                    )
                                    await message.reply(f"{reply_text}\n*(Opened **{thread_name}** in {matched_forum_channel.mention})*")

                                # Target is a Standard Text Channel (or default current channel)
                                else:
                                    target_chan = matched_text_channel if matched_text_channel else message.channel
                                    new_thread = await target_chan.create_thread(
                                        name=thread_name,
                                        type=discord.ChannelType.public_thread
                                    )
                                    await new_thread.send(forum_body)

                                    if target_chan != message.channel:
                                        await message.reply(f"{reply_text}\n*(Started **{thread_name}** in {target_chan.mention})*")
                                    else:
                                        await message.reply(f"{reply_text}\n*(Started **{thread_name}** right here!)*")

                            except Exception as e:
                                await message.reply(f"I tried to create the post, but hit an issue: {e}")
                                print(f"Error creating thread/forum post: {e}")

                        else:
                            # Action is "none" or standard conversation reply
                            await message.reply(reply_text)

                    else:
                        await message.reply("Oops, my fox ears got tangled processing that response! Mind asking again, Senpai?")

                except Exception as e:
                    print(f"Groq API Error: {e}")

    finally:
        # Clean up processed message ID
        processing_messages.discard(message.id)

client_discord.run(os.getenv("DISCORD_TOKEN"))
