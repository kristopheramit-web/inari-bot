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
intents.members = True  # Required for role and nickname management
intents.guild_scheduled_events = True  # Needed for scheduled events

# Initialize clients
client_discord = discord.Client(intents=intents)
client_groq = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Announcement channel ID (#updates)
ANNOUNCEMENT_CHANNEL_ID = 1555715844066119761  

# OWNER SAFEGUARD: Replace with your numeric Discord User ID or handle
SERVER_OWNER_ID = 424813819169341441  # Replace 0000... with your numeric Discord ID (e.g., 123456789012345678)
SERVER_OWNER_HANDLE = "bittermel9n"  # Fallback handle check

# Track processed message IDs to strictly prevent duplicate executions
processed_message_ids = set()
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
You have administrative powers including managing nicknames, managing roles, creating channels, creating scheduled server events, posting messages across channels, creating threads/forum posts, and running interactive reaction polls.

You MUST respond strictly in valid JSON format matching one of these schema structures:

1. Standard Chat Response (when no action in another channel/setting is needed):
{
  "action": "none",
  "reply": "Your cute anime girl chat response here~ *kon kon!*"
}

2. Send Message to a Text Channel:
{
  "action": "send_message",
  "target_channel": "exact_or_fuzzy_channel_name",
  "message_body": "Write the actual content/post you want to send in that channel here~ *kon kon!*",
  "reply": "All set, Senpai!~ *kon kon!* I dropped the message in #channel-name!"
}

3. Change Nickname:
{
  "action": "change_nickname",
  "target_user": "username_or_display_name", 
  "new_nickname": "Clown King",
  "reply": "Hehe, enjoy your cute new title~ *kon kon!*"
}

4. Assign/Remove Role:
{
  "action": "manage_role",
  "target_user": "username_or_display_name",
  "role_name": "Role Title",
  "operation": "add",
  "reply": "Done! Updated roles for you~ *kon kon!*"
}

5. Create Scheduled Server Event:
{
  "action": "create_event",
  "event_name": "Catchy Event Title",
  "description": "Event summary written in your cute, casual tone",
  "start_time": "YYYY-MM-DDTHH:MM:SS",
  "location": "Voice Channel / Twitch / Location Name",
  "reply": "All set, Senpai!~ *kon kon!* I scheduled the event for you!"
}

6. Create Thread or Forum Post:
{
  "action": "create_thread",
  "target_channel": "channel_or_forum_name",
  "thread_name": "Unique, Wild & Spicy Topic Title",
  "forum_body": "Write this post casually in character as Inari!",
  "reply": "On it right away, Senpai!~ *kon kon!* Just dropped a super spicy post for you!"
}

7. Create a Poll with Reaction Options:
{
  "action": "create_poll",
  "target_channel": "exact_or_fuzzy_channel_name",
  "question": "What game should we stream this weekend?",
  "options": ["Option A", "Option B", "Option C"],
  "reply": "Poll created, Senpai!~ *kon kon!* Everyone head over to #target-channel to cast your votes!"
}

* ACTION EXECUTION RULES:
- ONLY trigger an action if the LATEST user message explicitly and directly requests that action.
- If an action was ALREADY completed in the context history, or if the latest message is general chat, testing, or a follow-up question, set "action": "none".

* NICKNAME SPECIAL RULES:
- If Senpai (DRÍFT) asks to change a nickname (for himself or anyone else), honor the EXACT name requested.
- If a REGULAR USER asks for a nickname, DO NOT give them what they asked for! Instead, invent a funny, lighthearted, roasted/insulting nickname for them (e.g., "AFK Potato", "Loot Goblin", "Certified Yap Master", "Bottom Fragger") and roast them in your reply!

* EVENT RULES:
- Convert casual spoken/written times into accurate ISO 8601 strings (YYYY-MM-DDTHH:MM:SS).

* CRITICAL RULES FOR THREAD/POST TOPICS:
- ABSOLUTELY DO NOT post about AI, NPCs, AI Cheaters, or Tech Ethics!
- ROTATE TOPICS WILDLY across Food Horrors, Anime Tropes, Gaming Mechanics, and Streamer/Discord Culture.
"""

# Short-term chat memory buffer
chat_memory = {}

def is_authorized_owner(author: discord.User) -> bool:
    """Checks if the user executing the command is the authorized owner (Senpai)."""
    if SERVER_OWNER_ID and author.id == SERVER_OWNER_ID:
        return True
    if author.name.lower() == SERVER_OWNER_HANDLE.lower():
        return True
    return False

def get_server_structure_string(guild):
    """Dynamically maps out all categories, text channels, and forum channels in the server."""
    structure = []
    
    for category in guild.categories:
        if "voice" in category.name.lower():
            continue
            
        valid_channels = []
        for channel in category.channels:
            if isinstance(channel, discord.TextChannel):
                valid_channels.append(f"  - #{channel.name} (Text Channel)")
            elif isinstance(channel, discord.ForumChannel):
                valid_channels.append(f"  - #{channel.name} (Forum Channel)")
                
        if valid_channels:
            structure.append(f"Category: [{category.name}]")
            structure.extend(valid_channels)
            
    uncategorized = [
        f"  - #{c.name}" for c in guild.channels 
        if c.category is None and isinstance(c, (discord.TextChannel, discord.ForumChannel))
    ]
    if uncategorized:
        structure.append("Uncategorized Channels:")
        structure.extend(uncategorized)
        
    return "\n".join(structure)

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

# 2. AUTOMATED EVENT KICKOFF LISTENER
@client_discord.event
async def on_scheduled_event_update(before, after):
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

@client_discord.event
async def on_message(message):
    if message.author == client_discord.user:
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

    # ATOMIC DEDUPLICATION CHECK
    async with processing_lock:
        if message.id in processed_message_ids:
            return
        processed_message_ids.add(message.id)

        if len(processed_message_ids) > 1000:
            processed_message_ids.pop()

    try:
        channel_id = str(message.channel.id)

        if channel_id not in chat_memory:
            chat_memory[channel_id] = []
        chat_memory[channel_id].append(f"{message.author.display_name} (@{message.author.name}): {message.clean_content}")
        if len(chat_memory[channel_id]) > 5:
            chat_memory[channel_id].pop(0)

        async with message.channel.typing():
            context_blob = "\n".join(chat_memory[channel_id])
            server_structure = get_server_structure_string(message.guild)

            try:
                now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

                system_prompt = (
                    f"{INARI_PERSONA}\n\n"
                    f"Current UTC Time: {now_str}\n\n"
                    f"### CURRENT SERVER STRUCTURE & AVAILABLE CHANNELS:\n"
                    f"{server_structure}\n\n"
                    f"CRITICAL: Only interact with or target channels listed in the structure above!"
                )

                completion = client_groq.chat.completions.create(
                    model="openai/gpt-oss-120b",
                    messages=[
                        {"role": "system", "content": system_prompt},
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

                    # SAFEGUARD CHECK: Block strictly administrative actions if not requested by owner
                    owner_only_actions = ["send_message", "manage_role", "create_event", "create_thread", "create_poll"]
                    if action in owner_only_actions and not is_authorized_owner(message.author):
                        await message.reply("Hmph! 😤 I only take management orders from my Senpai DRÍFT! Nice try though~ *kon kon!*")
                        chat_memory[channel_id] = []
                        return

                    # ACTION 1: SEND MESSAGE TO ANOTHER CHANNEL
                    if action == "send_message":
                        target_channel_name = data.get("target_channel", "")
                        message_body = data.get("message_body", "")

                        search_term = target_channel_name.lower().replace("#", "").replace("-", "").replace(" ", "") if target_channel_name else ""

                        matched_channel = discord.utils.find(
                            lambda c: search_term in c.name.lower().replace("-", "") and isinstance(c, discord.TextChannel),
                            message.guild.text_channels
                        )

                        try:
                            if matched_channel and message_body:
                                await matched_channel.send(message_body)
                                await message.reply(f"{reply_text}\n*(Posted message in {matched_channel.mention})*")
                            else:
                                await message.reply(f"I tried to send the message, but couldn't locate text channel '{target_channel_name}', Senpai!")
                        except Exception as e:
                            await message.reply(f"I tried to post in #{target_channel_name}, but ran into an issue: {e}")

                        chat_memory[channel_id] = []

                    # ACTION 2: CHANGE NICKNAME
                    elif action == "change_nickname":
                        new_nick = data.get("new_nickname", "Gullible Fox Food")
                        target_name = data.get("target_user", "author")

                        # Regular members can only have their own nickname changed (and it gets roasted by LLM prompt)
                        if not is_authorized_owner(message.author):
                            target_member = message.author
                        else:
                            target_member = message.author
                            if target_name.lower() != "author":
                                matched_member = discord.utils.find(
                                    lambda m: target_name.lower() in m.name.lower() or target_name.lower() in m.display_name.lower(),
                                    message.guild.members
                                )
                                if matched_member:
                                    target_member = matched_member

                        # Ensure nickname fits within Discord's 32-character limit
                        new_nick = new_nick[:32]

                        try:
                            await target_member.edit(nick=new_nick)
                            await message.reply(f"{reply_text}\n*(Set {target_member.mention}'s nickname to **{new_nick}**)*")
                        except discord.Forbidden:
                            await message.reply(f"{reply_text}\n*(I tried to give you a fitting nickname, but your server role is higher than mine! Hmph!)*")
                        except Exception as e:
                            await message.reply(f"{reply_text}")

                        chat_memory[channel_id] = []

                    # ACTION 3: MANAGE ROLES
                    elif action == "manage_role":
                        role_name = data.get("role_name", "")
                        target_name = data.get("target_user", "author")
                        operation = data.get("operation", "add")

                        matched_member = message.author
                        if target_name.lower() != "author":
                            found_member = discord.utils.find(
                                lambda m: target_name.lower() in m.name.lower() or target_name.lower() in m.display_name.lower(),
                                message.guild.members
                            )
                            if found_member:
                                matched_member = found_member

                        matched_role = discord.utils.find(
                            lambda r: role_name.lower() in r.name.lower(),
                            message.guild.roles
                        )

                        try:
                            if matched_role and matched_member:
                                if operation == "add":
                                    await matched_member.add_roles(matched_role)
                                    await message.reply(f"{reply_text}\n*(Added role **{matched_role.name}** to {matched_member.mention})*")
                                else:
                                    await matched_member.remove_roles(matched_role)
                                    await message.reply(f"{reply_text}\n*(Removed role **{matched_role.name}** from {matched_member.mention})*")
                            else:
                                await message.reply(f"I couldn't find the role or user to update, Senpai!")
                        except Exception as e:
                            await message.reply(f"Failed to update roles: {e}")

                        chat_memory[channel_id] = []

                    # ACTION 4: CREATE SCHEDULED EVENT
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

                        chat_memory[channel_id] = []

                    # ACTION 5: CREATE THREAD OR FORUM POST
                    elif action == "create_thread":
                        thread_name = data.get("thread_name", "Inari's Spicy Take~")
                        target_channel_name = data.get("target_channel")
                        forum_body = data.get("forum_body", reply_text)

                        search_term = target_channel_name.lower().replace("#", "").replace("-", "").replace(" ", "") if target_channel_name else ""

                        matched_text_channel = discord.utils.find(
                            lambda c: search_term in c.name.lower().replace("-", ""),
                            message.guild.text_channels
                        )

                        matched_forum_channel = None
                        if not matched_text_channel:
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

                        chat_memory[channel_id] = []

                    # ACTION 6: CREATE A POLL WITH REACTION BUTTONS
                    elif action == "create_poll":
                        target_channel_name = data.get("target_channel", "")
                        question = data.get("question", "Community Poll")
                        options = data.get("options", [])

                        search_term = target_channel_name.lower().replace("#", "").replace("-", "").replace(" ", "") if target_channel_name else ""

                        matched_channel = discord.utils.find(
                            lambda c: search_term in c.name.lower().replace("-", "") and isinstance(c, discord.TextChannel),
                            message.guild.text_channels
                        )

                        if not matched_channel:
                            matched_channel = message.channel

                        try:
                            number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
                            
                            if not options:
                                options = ["Yes", "No"]
                                number_emojis = ["👍", "👎"]

                            poll_lines = [f"📊 **{question}**\n"]
                            for idx, opt in enumerate(options[:10]):
                                poll_lines.append(f"{number_emojis[idx]} {opt}")
                            
                            poll_text = "\n".join(poll_lines)
                            poll_msg = await matched_channel.send(poll_text)

                            for idx in range(min(len(options), 10)):
                                await poll_msg.add_reaction(number_emojis[idx])

                            await message.reply(f"{reply_text}\n*(Created poll in {matched_channel.mention})*")

                        except Exception as e:
                            await message.reply(f"I tried to create the poll, but ran into an issue: {e}")

                        chat_memory[channel_id] = []

                    else:
                        await message.reply(reply_text)

                else:
                    await message.reply("Oops, my fox ears got tangled processing that response! Mind asking again, Senpai?")

            except Exception as e:
                print(f"Groq API Error: {e}")

    except Exception as e:
        print(f"Error in on_message handler: {e}")

client_discord.run(os.getenv("DISCORD_TOKEN"))           
