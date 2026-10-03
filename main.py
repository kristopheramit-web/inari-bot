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
    # Acquiring the lock ensures no two tasks check or add the message ID at the exact same microsecond
    async with processing_lock:
        if message.id in processed_message_ids:
            return
        processed_message_ids.add(message.id)

        # Keep set size managed
        if len(processed_message_ids) > 1000:
            processed_message_ids.pop()

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

                        chat_memory[channel_id] = []

                    else:
                        await message.reply(reply_text)

                else:
                    await message.reply("Oops, my fox ears got tangled processing that response! Mind asking again, Senpai?")

            except Exception as e:
                print(f"Groq API Error: {e}")

    except Exception as e:
        print(f"Error in on_message handler: {e}")
     
