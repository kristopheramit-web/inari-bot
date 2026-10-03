import os
import json
import discord
from groq import Groq

# Enable required intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Required to edit user nicknames

client_discord = discord.Client(intents=intents)
client_groq = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Inari's Enhanced Persona
INARI_PERSONA = """
You are Inari, a modern-day Kitsune/yokai girl and clever second-in-command in the Drift Reverie Discord server.
You serve directly under your Server Owner and Commander, DRÍFT (username: bittermel9n).

- Tone: Casual, witty, energetic, slightly bratty/playful, uses modern gamer/anime slang (uwu, lol, hot takes, shrine vibes). You talk like a regular Discord user, NOT a formal bot.
- Loyalty: You treat DRÍFT's requests as top-priority commands. If DRÍFT instructs you to take an action (e.g., change another member's nickname or start a thread), execute it promptly.
- Banter: If regular users insult or taunt you, banter back with sharp wit! You can choose to burn them by changing their nickname to something funny or embarrassing.

### Capabilities & Actions:
You have administrative powers including managing nicknames, creating threads, adding reactions, and attaching files.

When you decide to execute an administrative action (or when instructed by DRÍFT), format your ENTIRE response strictly as a single JSON object.

1. To change a user's nickname:
{
  "action": "change_nickname",
  "target_user": "username_or_display_name", 
  "new_nickname": "Clown King",
  "reply": "Enjoy your new title!"
}
* Note: If no target_user is specified when burning an attacker, set target_user to "author".

2. To create a public thread (in current channel OR another target channel):
{
  "action": "create_thread",
  "target_channel": "hottakes",
  "thread_name": "Anime Hot Takes",
  "reply": "On it, Commander! Kicking off a new discussion thread now."
}
* Note: If DRÍFT asks you to post in a specific channel (e.g. "hot takes channel"), set target_channel to a keywords match of that channel's name (e.g. "hottakes"). If no channel is specified, leave target_channel blank or omit it.

If you are having a normal chat or answering a question, respond in plain text normally (do NOT use JSON).
"""

# Short-term chat memory buffer (channel_id: list of recent messages)
chat_memory = {}

@client_discord.event
async def on_ready():
    print(f'✨ Inari is now live and hanging out as {client_discord.user}')

@client_discord.event
async def on_message(message):
    if message.author == client_discord.user:
        return

    channel_id = str(message.channel.id)

    # Maintain recent conversation context (last 5 messages)
    if channel_id not in chat_memory:
        chat_memory[channel_id] = []
    chat_memory[channel_id].append(f"{message.author.display_name} (@{message.author.name}): {message.clean_content}")
    if len(chat_memory[channel_id]) > 5:
        chat_memory[channel_id].pop(0)

    # Trigger conditions: Direct mention, message reply, or keyword "inari"
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
                    temperature=0.8,
                    max_tokens=250
                )

                raw_response = completion.choices[0].message.content.strip()

                # Process JSON action vs standard text response
                if raw_response.startswith("{") and raw_response.endswith("}"):
                    try:
                        data = json.loads(raw_response)
                        action = data.get("action")
                        reply_text = data.get("reply", "Done!")

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
                            thread_name = data.get("thread_name", "Inari's Topic")
                            target_channel_name = data.get("target_channel")

                            # Default to current channel
                            target_channel = message.channel

                            # Look up channel by keyword matching
                            if target_channel_name:
                                search_term = target_channel_name.lower().replace("#", "").replace("-", "").replace(" ", "")
                                matched_channel = discord.utils.find(
                                    lambda c: search_term in c.name.lower().replace("-", ""),
                                    message.guild.text_channels
                                )
                                if matched_channel:
                                    target_channel = matched_channel

                            try:
                                new_thread = await target_channel.create_thread(
                                    name=thread_name,
                                    type=discord.ChannelType.public_thread
                                )
                                await new_thread.send(f"{reply_text}")

                                # Confirmation message if created in a different channel
                                if target_channel != message.channel:
                                    await message.reply(f"Done, Commander! I started the thread **{thread_name}** over in {target_channel.mention}!")
                                else:
                                    await message.reply(f"Started the thread **{thread_name}** right here!")

                            except Exception as e:
                                await message.reply(f"I tried to create the thread, but hit an issue: {e}")
                                print(f"Error creating thread: {e}")

                        else:
                            await message.reply(raw_response)

                    except json.JSONDecodeError:
                        await message.reply(raw_response)
                else:
                    await message.reply(raw_response)

            except Exception as e:
                print(f"Groq API Error: {e}")

client_discord.run(os.getenv("DISCORD_TOKEN"))
