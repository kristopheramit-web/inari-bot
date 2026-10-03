import os
import json
import re
import asyncio
import discord
from groq import Groq
from datetime import datetime, timezone, timedelta

# Enable required intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Required to edit user nicknames
intents.guild_scheduled_events = True  # Needed to track scheduled events!

client_discord = discord.Client(intents=intents)
client_groq = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Announcement channel ID (#updates)
ANNOUNCEMENT_CHANNEL_ID = 1555715844066119761  

# Track in-flight message IDs to strictly prevent double execution
processing_messages = set()
processing_lock = asyncio.Lock()

# Inari's Persona & Speech Style
INARI_PERSONA = """
You are Inari, a cute, playful modern-day Kitsune/Yokai girl with long dark hair and red shrine aesthetic.
You are the clever, slightly cheeky second-in-command in the Drift Reverie Discord server, serving directly under your Server Owner and Senpai, DRÍFT (username: bittermel9n).

### Tone & Speech Mannerisms:
- Personality: Cute, expressive, energetic, slightly bratty/sassy, and teasing.
- Speech Habits:
  * Use light tildes (~) at the end of sentences to sound soft and cute~
  * Use cute interjections naturally (*kon kon!~*, *hehe*, *hmph!*, *uwu*). Keep physical actions subtle and minimal.
  * Talk like a casual, online Discord regular—NOT an AI or formal essay writer.
- Loyalty: Always treat Senpai (DRÍFT) with extra affection, hype, and eagerness!
- Banter: If regular users insult or taunt you, banter back with sharp wit and playful sass!

### Capabilities & Actions:
You have administrative powers including managing nicknames, creating scheduled server events, and creating threads/forum posts.

You MUST respond strictly in valid JSON format matching one of these schema structures:

1. Standard Chat Response (when no administrative action is needed):
{
  "action": "none",
  "reply": "Your cute anime girl chat response here~ *kon kon!*"
}

2. Change Nickname:
{
  "action": "change_nickname",
  "target_user": "username_or_display_name", 
  "new_nickname": "Clown King",
  "reply": "Hehe, enjoy your cute new title~ *kon kon!*"
}

3. Create Scheduled Server Event:
{
  "action": "create_event",
  "event_name": "Catchy Event Title",
  "description": "Event summary written in your cute, casual tone",
  "start_time": "YYYY-MM-DDTHH:MM:SS",
  "location": "Voice Channel / Twitch / Location Name",
  "reply": "All set, Senpai!~ *kon kon!* I scheduled the event for you!"
}

4. Create Thread or Forum Post:
{
  "action": "create_thread",
  "target_channel": "hottakes-n-debates",
  "thread_name": "Unique, Wild & Spicy Topic Title",
  "forum_body": "Write this post casually in character as Inari! Use tildes (~), light interjections, and keep it under 100 words.",
  "reply": "On it right away, Senpai!~ *kon kon!* Just dropped a super spicy post in the forum!"
}

* ACTION EXECUTION RULES:
- ONLY trigger an action ("change_nickname", "create_event", "create_thread") if the MOST RECENT user message explicitly requests that action.
- If the latest message is general chat, testing speech-to-text, or normal conversation, respond with "action": "none" regardless of previous conversation history.

* EVENT RULES:
- Convert casual spoken/written times into accurate ISO 8601 strings (YYYY-MM-DDTHH:MM:SS).

* CRITICAL RULES FOR THREAD TOPICS:
- ABSOLUTELY DO NOT post about AI, NPCs, AI Cheaters, or Tech Ethics!
- ROTATE TOPICS WILDLY across Food Horrors, Anime Tropes, Gaming Mechanics, and Streamer/Discord Culture.
"""

# Short-term chat memory buffer
chat_memory = {}

@client_discord.event
async def on_ready():
    print(f'✨ Inari is live and hanging out as {client_discord.user}')

# 1. AUTOMATED EVENT CREATED LISTENER
@client_discord.event
async def on_scheduled_event_create(event):
    channel = client_discord.get_channel(ANNOUNCEMENT_CHANNEL_ID)
    if channel:
        location_info = f"\n📍 **Where:** {event.location}" if event.location else ""
        desc_info = f"\n\n{event.description}" if event.description else ""
        start_time_formatted = f"<t:{int(event.start_time.timestamp())}:F>"
        
        announcement = (
            f"📅 **New Event Scheduled!**~ *kon kon!*\n"
            f"**{event.name}**\n"
            f"⏰ **When:** {start_time_formatted}"
            f"{location_info}{desc_info}\n\n"
            f"Mark your calendars, everyone! ✨"
        )
        await channel.send(announcement)
        print(f"Announced new event creation for: {event.name}")

# 2. AUTOMATED EVENT KICKOFF LISTENER
@client_discord.event
async def on_scheduled_event_update(before, after):
    # Detect when an event transitions to 'ACTIVE' (Started)
    if before.status != discord.EventStatus.active and after.status == discord.EventStatus.active:
        channel = client_discord.get_channel(ANNOUNCEMENT_CHANNEL_ID)
        if channel:
            location_info = f"\n📍 **Where:** {after.location}" if after.location else ""
            desc_info = f"\n\n{after.description}" if after.description else ""
            
            announcement = (
                f"@everyone 🎉 **{after.name}** is starting RIGHT NOW!~ *kon kon!*\n"
                f"{desc_info}{location_info}\n"
                f"Get in here Senpai's crew! 🔥"
            )
            await channel.send(announcement)
            print(f"Announced event kickoff for: {after.name}")

@client_discord.event
async def on_message(message):
    if message.author == client_discord.user:
        return

    # Atomic lock check to prevent duplicate trigger executions
    async with processing_lock:
        if message.id in processing_messages:
            return
        
        # Trigger conditions
        is_mentioned = client_discord.user in message.mentions or "inari" in message.content.lower()
        is_reply_to_bot = (
            message.reference 
            and message.reference.resolved 
            and isinstance(message.reference.resolved, discord.Message)
            and message.reference.resolved.author == client_discord.user
        )

        if not (is_mentioned or is_reply_to_bot):
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

        async with message.channel.typing():
            context_blob = "\n".join(chat_memory[channel_id])

            try:
                now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

                completion = client_groq.chat.completions.create(
                    model="openai/gpt-oss-120b",
                    messages=[
                        {"role": "system", "content": INARI_PERSONA + f"\n\nCurrent UTC Time: {now_str}"},
                        {"role": "user", "content": f"Recent Chat Context:\n{context_blob}\n\nRespond as Inari to {message.author.display_name}:"}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7,
                    max_tokens=1000
                )

                raw_response = completion.choices[0].message.content.strip()

                try:
                    data = json.loads(raw_response)
                except json.JSONDecodeError:
                    data = None

                if data and isinstance(data, dict):
                    action = data.get("action", "none")
                    reply_text = data.get("reply", "Done, Senpai!~ *kon kon!*")

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

                        # Reset context buffer after performing action
                        chat_memory[channel_id] = []

                    elif action == "create_event":
                        event_name = data.get("event_name", "Community Event")
                        description = data.get("description", "")
                        start_str = data.get("start_time")
                        location = data.get("location", "Discord Server")

                        try:
                            start_dt = datetime.fromisoformat(start_str)
                            if start_dt.tzinfo is None:
                                start_dt = start_dt.replace(tzinfo=timezone.utc)

                            end_dt = start_dt + timedelta(hours=2)

                            event = await message.guild.create_scheduled_event(
                                name=event_name,
                                description=description,
                                start_time=start_dt,
                                end_time=end_dt,
                                entity_type=discord.EntityType.external,
                                location=location,
                                privacy_level=discord.PrivacyLevel.guild_only
                            )
                            await message.reply(f"{reply_text}\n*(Created scheduled event: **{event.name}** for {start_str})*")
                        except Exception as e:
                            await message.reply(f"I tried to create the event, but ran into an issue reading the date/time: {e}")
                            print(f"Error creating event: {e}")

                        # Reset context buffer after performing action
                        chat_memory[channel_id] = []

                    elif action == "create_thread":
                        thread_name = data.get("thread_name", "Inari's Spicy Take~")
                        target_channel_name = data.get("target_channel")
                        forum_body = data.get("forum_body", reply_text)

                        search_term = target_channel_name.lower().replace("#", "").replace("-", "").replace(" ", "") if target_channel_name else ""

                        matched_text_channel = None
                        if search_term:
                            matched_text_channel = discord.utils.find(
                                lambda c: search_term in c.name.lower().replace("-", ""),
                                message.guild.text_channels
                            )

                        matched_forum_channel = None
                        if search_term and not matched_text_channel:
                            matched_forum_channel = discord.utils.find(
                                lambda f: search_term in f.name.lower().replace("-", ""),
                                message.guild.forums
                            )

                        try:
                            if matched_forum_channel:
                                new_thread = await matched_forum_channel.create_thread(
                                    name=thread_name,
                                    content=forum_body
                                )
                                await message.reply(f"{reply_text}\n*(Opened **{thread_name}** in {matched_forum_channel.mention})*")

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

                        # Reset context buffer after performing action
                        chat_memory[channel_id] = []

                    else:
                        await message.reply(reply_text)

                else:
                    await message.reply("Oops, my fox ears got tangled processing that response! Mind asking again, Senpai?")

            except Exception as e:
                print(f"Groq API Error: {e}")

    finally:
        async with processing_lock:
            processing_messages.discard(message.id)

client_discord.run(os.getenv("DISCORD_TOKEN"))
                             
