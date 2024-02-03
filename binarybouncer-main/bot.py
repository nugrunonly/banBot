from twitchAPI.twitch import Twitch
from twitchAPI.oauth import UserAuthenticator
from twitchAPI.type import AuthScope, ChatEvent
from twitchAPI.chat import Chat, EventData, ChatMessage, ChatCommand
from twitchAPI.helper import first
import asyncio
import os
import json
import openai
from urllib.request import urlopen
import datetime
from retrying import retry
from dotenv import load_dotenv

load_dotenv()

openai.api_key = os.environ['API_KEY']


class BinaryBouncer:
    def __init__(self, app_id, app_secret, user_scope, target_channel):
        self.app_id = app_id
        self.app_secret = app_secret
        self.user_scope = user_scope
        self.target_channel = target_channel
        self.twitch = None
        self.chat = None
        self.bot_id = '828159307'


    async def get_user_id(self, username):
        try:
            user = await first(self.twitch.get_users(logins=[username]))
            return user.id
        except Exception as e:
            print(f"Error: {e}")
            return None

    
    async def add_bot(self, botname, id):
        with open('alivebots.json') as d:
            old_data = json.load(d)
            old_data[botname] = id
            with open('alivebots.json', mode = 'w') as db:
                json.dump(old_data, db, indent = 2, ensure_ascii = False)
            print('added', botname, 'to the alive bots', id)

    async def del_bot(self, botname, id):
        with open('deadbots.json') as d:
            old_data = json.load(d)
            old_data[botname] = id
            with open('deadbots.json', mode = 'w') as db:
                json.dump(old_data, db, indent = 2, ensure_ascii = False)
            print('added', botname, 'to the dead bots', id)
            with open('alivebots.json') as ab:
                old_data = json.load(ab)
                if botname in old_data:
                    del old_data[botname]
                    with open('alivebots.json', mode = 'w') as ab:
                        json.dump(old_data, ab, indent = 2, ensure_ascii = False)
                    print('removed', botname, 'from the alive bots', id)
    
    async def build_banlist(self):
        url = 'https://api.twitchinsights.net/v1/bots/all'
        response = urlopen(url)
        botlist = json.loads(response.read())
        bots = botlist['bots']
        for name in range(len(bots)):
            user_id = await self.get_user_id(bots[name][0])
            if user_id == None:
                await self.del_bot(bots[name][0], user_id)
            else:
                await self.add_bot(bots[name][0], user_id)
            await asyncio.sleep(0.1)


    async def ban_user(self, username, channel_id, reason=None):
        user_id = await self.get_user_id(username)
        if user_id is None:
            print(f'Error: Could not find user {username}')
            await self.del_bot(username, user_id)
            return
        try:
            if reason is None:
                reason = "Bot"
            await self.twitch.ban_user(channel_id, self.bot_id, user_id, reason)
            print(f'Banned user {username} from channel ({channel_id})')
        except KeyError as e:
            if e.args and e.args[0] == 'data':
                print(f'Error: The "data" key is missing in the response while banning user {username} in channel {channel_id}.')
                await self.force_leave(channel_id)
                print('Bot does not have moderator permissions in channel so we left:', channel_id)
            else:
                print(f'KeyError: {e}. User {username} not banned in channel {channel_id}, likely already banned or does not exist.')

        except Exception as e:
            print(f'An unexpected error occurred while banning user {username} in channel {channel_id}: {e}')




        
    async def unban_user(self, username, channel_id):
        user_id = await self.get_user_id(username)
        if user_id is None:
            print(f'Error: Could not find user {username}')
            return
        try:
            await self.twitch.unban_user(channel_id, self.bot_id, user_id)
            print(f'Unbanned user {username} from channel ({channel_id})')
        except Exception as e:
            print(f"{self.bot_id} - Error {e}")
            return None
        

    async def on_ready(self, ready_event: EventData):
        print('Bot is ready for work, joining channels')
        await ready_event.chat.join_room(self.target_channel)
        # await self.force_join('noxid_art')
        await self.loop_stuff()


    async def on_message(self, msg: ChatMessage):
        print(f'in {msg.room.name}, {msg.user.name} said: {msg.text}')


    async def join(self, cmd: ChatCommand):
        id = await self.get_user_id(cmd.user.name)
        with open('channels.json') as c:
            old_data = json.load(c)
            if cmd.user.name not in old_data:
                old_data[cmd.user.name] = id
                with open('channels.json', mode = 'w') as c:
                    json.dump(old_data, c, indent = 2, ensure_ascii = False)
                print(cmd.user.name, 'added to the Bot-Free zone -- ID: ', id)
                await self.super_ban(cmd.user.name, id)

    async def force_join(self, name):
        id = await self.get_user_id(name)
        with open('channels.json') as c:
            old_data = json.load(c)
            if name not in old_data:
                old_data[name] = id
                with open('channels.json', mode = 'w') as c:
                    json.dump(old_data, c, indent = 2, ensure_ascii = False)
                print(name, 'added to the Bot-Free zone -- ID: ', id)
                await self.super_ban(name, id)


    async def rejoin(self, username):
        id = await self.get_user_id(username)
        with open('channels.json') as c:
            old_data = json.load(c)
            if username not in old_data:
                old_data[username] = id
                with open('channels.json', mode = 'w') as c:
                    json.dump(old_data, c, indent = 2, ensure_ascii = False)
                print(username, 'added to the Bot-Free zone -- ID: ', id)
                await self.super_ban(username, id)
                with open('totalJoined.txt', 'r+') as totalJoined:
                    counter = int(totalJoined.read().strip())
                    counter += 1
                    totalJoined.seek(0)
                    totalJoined.write(str(counter))
                    totalJoined.truncate()
                print("totalJoined incremented to:", counter)
                    

    async def leave_channel(self, cmd: ChatCommand):
        id = await self.get_user_id(cmd.user.name)
        with open('channels.json') as c:
            old_data = json.load(c)
            if cmd.user.name in old_data:
                formatted_date = datetime.datetime.now().strftime('%H:%M:%S %m/%d/%Y')
                print('Removing a channel -- ', {cmd.user.name}, 'at ', formatted_date)
                text = f'You have left the bot-free zone, {cmd.user.name}, New bots will no longer be banned on your channel.'
                await self.chat.send_message('binarybouncer', text)
                await self.twitch.remove_channel_moderator(id, '828159307')
                with open('channels.json') as c:
                    old_data = json.load(c)
                    if cmd.user.name in old_data:
                        del old_data[cmd.user.name]
                        with open('channels.json', mode = 'w') as c:
                            json.dump(old_data, c, indent = 2, ensure_ascii = False)
                        print(cmd.user.name, '- You have left the bot-free zone', id)
                with open('totalJoined.txt', 'r+') as totalJoined:
                    counter = int(totalJoined.read().strip())
                    counter -= 1
                    totalJoined.seek(0)
                    totalJoined.write(str(counter))
                    totalJoined.truncate()
                print("totalJoined decremented to:", counter)



    async def force_leave(self, id):
        try:
            with open('channels.json', 'r') as c:
                channels_data = json.load(c)
            str_id = str(id)
            username = next((name for name, channel_id in channels_data.items() if str(channel_id) == str_id), None)
            if username is None:
                print('No channel found for given ID:', str_id)
                return
            formatted_date = datetime.datetime.now().strftime('%H:%M:%S %m/%d/%Y')
            print('Removing a channel -- ', username, 'at ', formatted_date)  
            text = f'@{username}, BinaryBouncer needs to be a moderator on your channel to work!'
            await self.chat.send_message('binarybouncer', text)
            if username in channels_data:
                del channels_data[username]
                with open('channels.json', 'w') as c:
                    json.dump(channels_data, c, indent=2, ensure_ascii=False)
                print(username, '- You have left the bot-free zone', str_id)
            with open('totalJoined.txt', 'r+') as totalJoined:
                counter = int(totalJoined.read().strip())
                counter -= 1
                totalJoined.seek(0)
                totalJoined.write(str(counter))
                totalJoined.truncate()
            print("Total joined decremented to:", counter)
        except json.JSONDecodeError:
            print('Error: Could not decode JSON from channels.json')
        except Exception as e:
            print('An unexpected error occurred:', e)
 

    async def super_leave(self, cmd: ChatCommand):
        id = await self.get_user_id(cmd.user.name)
        with open('channels.json') as c:
            old_data = json.load(c)
            if cmd.user.name in old_data:
                formatted_date = datetime.datetime.now().strftime('%H:%M:%S %m/%d/%Y')
                print('Removing a channel -- ', {cmd.user.name}, 'at ', formatted_date)
                text = f'You have left the bot-free zone, {cmd.user.name}. New bots will no longer be banned on your channel.'
                await self.chat.send_message('binarybouncer', text)
                with open('channels.json') as c:
                    old_data = json.load(c)
                    if cmd.user.name in old_data:
                        del old_data[cmd.user.name]
                        with open('channels.json', mode = 'w') as c:
                            json.dump(old_data, c, indent = 2, ensure_ascii = False)
                        print(cmd.user.name, '- You have left the bot-free zone', id)
        with open('totalJoined.txt', 'r+') as totalJoined:
            counter = int(totalJoined.read().strip())
            counter -= 1
            totalJoined.seek(0)
            totalJoined.write(str(counter))
            totalJoined.truncate()
        print("totalJoined decremented to:", counter)
        await self.mass_unban(cmd.user.name, id)
        await self.twitch.remove_channel_moderator(id, '828159307')
    

    async def mass_unban(self, username, id):
        await self.chat.send_message('binarybouncer', f'Starting mass unbanning of bots on {username}\'s channel. This can take a while, please be patient and do not unmod BinaryBouncer until it is over...')
        finished = True
        with open('alivebots.json') as activebots:
            active_bots = json.load(activebots)
            for active in active_bots:
                print(f'Mass removal on {username}\'s channel -- {active}, {active_bots[active]}')
                try:
                    await self.unban_user(active, id)
                except Exception as e:
                    await self.chat.send_message('binarybouncer', f'@{username}, Please add BinaryBouncer as a moderator and try again.')
                    print(f'No mod privileges on channel {username}, stopping mass unban. Error {e}')
                    with open('channels.json') as c:
                        old_data = json.load(c)
                        if username not in old_data:
                            old_data[username] = id
                            with open('channels.json', mode = 'w') as c:
                                json.dump(old_data, c, indent = 2, ensure_ascii = False)
                    finished = False
                    break
        if finished:
            await self.chat.send_message('binarybouncer', f'Finished unbanning all bots on {username}\'s channel.')


    async def super_ban(self, channel, id):
        finished = True   
        await self.chat.send_message('binarybouncer', f'Starting mass exodus of bots on {channel}\'s channel. This can take a while (~50min), please be patient...')
        with open('alivebots.json') as activebots:
            active_bots = json.load(activebots)
            for active in active_bots:
                print(f'Mass exodus on {channel}\'s channel -- {active}, {active_bots[active]}')
                if finished:
                    try:
                        await self.ban_user(active, id)
                    except Exception as e:
                        print(f'No mod privileges on channel {channel}, stopping the superban. Error {e}')
                        with open('channels.json') as c:
                            old_data = json.load(c)
                            if channel in old_data:
                                del old_data[channel]
                                with open('channels.json', mode = 'w') as c:
                                    json.dump(old_data, c, indent = 2, ensure_ascii = False)
                        finished = False
                        break
                    await asyncio.sleep(0.4)
                else:
                    await self.chat.send_message('binarybouncer', f'@{channel}, Please add BinaryBouncer as a moderator and try again.')
                    break
        if finished:
            await self.chat.send_message('binarybouncer', f'Finished banning all bots on {channel}\'s channel.')
            with open('joinhistory.txt', 'r+') as joinHistory:
                joinHistory.write(f'{channel}\n')
                print('Added', channel, 'to the join history')
            with open('totalJoined.txt', 'r+') as totalJoined:
                counter = int(totalJoined.read().strip())
                counter += 1
                totalJoined.seek(0)
                totalJoined.write(str(counter))
                totalJoined.truncate()
            print("totalJoined incremented to:", counter)


    async def add_limerick(self, cmd: ChatCommand):
        with open('channels.json') as c:
            old_data = json.load(c)
            if cmd.user.name in old_data:
                with open('limerick.txt', 'r+') as limerick:
                    lim = limerick.read()
                    if cmd.user.name not in lim:
                        print('adding user', cmd.user.name, 'to the limericks')
                        limerick.write(f'{cmd.user.name}\n')
                        await self.chat.send_message('binarybouncer', f'{cmd.user.name} - You have been added to the silly limericks alerts')
            else:
                await self.chat.send_message('binarybouncer', f'Please join the bot-free zone to use this feature - {cmd.user.name}')


    async def del_limerick(self, cmd: ChatCommand):
        with open('limerick.txt', 'r') as limerick:
            lines = limerick.readlines()
            lines = [line for line in lines if cmd.user.name not in line]
        with open('limerick.txt', 'w') as limerick:
            limerick.writelines(lines)     
        print('Removed user ' + cmd.user.name + ' from the limericks')
        await self.chat.send_message('binarybouncer', f'{cmd.user.name} - You have been removed to the silly limericks alerts')


    @retry(stop_max_attempt_number=3, wait_fixed=2000)
    def create_prompt(self, prompt, command=False):
        print('attempting to create a prompt')
        return openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": f"In less than 300 characters, please write a limerick about a bot named {prompt} that got banned from Twitch."}], temperature=1.1)



    async def ban_routine(self):
        url = 'https://api.twitchinsights.net/v1/bots/all'
        response = urlopen(url)
        botlist = json.loads(response.read())
        bots = botlist['bots']
        formatted_date = datetime.datetime.now().strftime('%H:%M:%S %m/%d/%Y')
        with open('banlist.txt', 'r+') as banlist:
            banned = banlist.read()
            for name in range(len(bots)):
                if bots[name][0] not in banned:
                    print('new bot found', bots[name][0])
                    id = await self.get_user_id(bots[name][0])
                    await self.add_bot(bots[name][0], id)
                    banlist.write(f'{bots[name][0]}\n')
                    with open('channels.json') as channels:
                        c = json.load(channels)
                        for ch in c:
                            await self.ban_user(bots[name][0], c[ch])
                            await asyncio.sleep(0.4)
                    with open('totalBots.txt', 'r+') as totalBots:
                        counter = int(totalBots.read().strip())
                        counter += 1
                        totalBots.seek(0)
                        totalBots.write(str(counter))
                        totalBots.truncate()
                    with open('lastBan.txt', 'w') as lastBan:
                        lastBan.write(bots[name][0])
                    print("totalBots incremented to:", counter)
                    print('telling a sad story about', bots[name][0], 'getting banned')
                    prompt = bots[name][0]
                    try:
                        completion = self.create_prompt(prompt, command=True)
                        print(f'sad story about {prompt}', completion)
                        with open('limerick.txt', 'r') as limericks:
                            for line in limericks:
                                chan = line.strip() 
                                await self.chat.send_message(chan, completion.choices[0].message.content)
                                await asyncio.sleep(0.4)

                    except Exception as e:
                        print('found error', e)
        print('Super_Ban list Updated at', formatted_date)
        with open('lastRoutine.txt', 'w') as lastRoutine:
            lastRoutine.write(formatted_date)
        return


    async def run_periodically(self, coro, interval_seconds):
        while True:
            await asyncio.sleep(interval_seconds)
            await coro()


    async def loop_stuff(self):
        interval_seconds = 900
        coro = self.ban_routine
        await coro()
        asyncio.create_task(self.run_periodically(coro, interval_seconds))
        

    async def run(self):
        self.twitch = await Twitch(self.app_id, self.app_secret)
        auth = UserAuthenticator(self.twitch, self.user_scope)
        token, refresh_token = await auth.authenticate()

        await self.twitch.set_user_authentication(token, self.user_scope, refresh_token)

        self.chat = await Chat(self.twitch)
        self.chat.register_event(ChatEvent.READY, self.on_ready)
        self.chat.register_event(ChatEvent.MESSAGE, self.on_message)
        self.chat.register_command('join', self.join)
        self.chat.register_command('leave', self.leave_channel)
        self.chat.register_command('ilovebots', self.super_leave)
        self.chat.register_command('alert', self.add_limerick)
        self.chat.register_command('noalert', self.del_limerick)
        self.chat.start()

        try:
            input('press ENTER to stop\n')
        finally:
            self.chat.stop()
            await self.twitch.close()


if __name__ == '__main__':
    APP_ID = os.environ['APP_ID']
    APP_SECRET = os.environ['APP_SECRET']
    USER_SCOPE = [AuthScope.CHAT_READ, AuthScope.CHAT_EDIT, AuthScope.MODERATOR_MANAGE_BANNED_USERS, AuthScope.CHANNEL_MANAGE_MODERATORS]
    TARGET_CHANNEL = 'binarybouncer'

    bouncer = BinaryBouncer(APP_ID, APP_SECRET, USER_SCOPE, TARGET_CHANNEL)
    asyncio.run(bouncer.run())
