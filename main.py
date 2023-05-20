import asyncio
import code
import contextlib
import disnake
import disnake.utils
import inspect
import logging
import sys
import traceback
from asyncio import ensure_future, gather
from asyncio import get_event_loop_policy
from asyncio.exceptions import InvalidStateError
from disnake.ext import commands
from disnake.ext.commands import Bot
from dotenv import load_dotenv
from functools import lru_cache
from os import getenv
from pathlib import Path
from threading import Event
from threading import Thread, current_thread
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from typing import List, Dict, Any

logging.root.setLevel(logging.DEBUG)
logging.root.addHandler(logging.StreamHandler())
log = logging.getLogger(__name__)
for log_name in (
    "disnake.__init__",
    "disnake.client",
    "disnake.gateway",
    "disnake.http",
    "disnake.opus",
    "disnake.player",
    "disnake.shard",
    "disnake.state",
    "disnake.voice_client",
    "disnake.webhook",
    "disnake.webhook",
    "watchdog.events",
    "watchdog.observers.fsevents",
    "watchdog.observers.fsevents2",
    "watchdog.observers.inotify_buffer",
):
    logging.getLogger(log_name).setLevel(logging.INFO)


load_dotenv()
DISCORD_BOT_TOKEN: str = (
  getenv("Token", "")
  or getenv("AliceToken", "")
)

orig_cwd = Path.cwd()

PREFIX = "."
command_sync_flags = commands.CommandSyncFlags.all()
command_sync_flags.sync_commands_debug = True
command_sync_flags.sync_on_cog_actions = True
command_sync_flags.sync_commands = True
command_sync_flags.sync_global_commands = True
command_sync_flags.sync_guild_commands = True
print(command_sync_flags)

for presences_enabled in (True, False):
  try:
    intents = disnake.Intents.default()
    intents.value |= disnake.Intents.messages.flag
    intents.value |= getattr(
      disnake.Intents, "message_content"
    ).flag
    intents.value |= disnake.Intents.guilds.flag
    intents.value |= disnake.Intents.members.flag
    if presences_enabled:
      intents.value |= disnake.Intents.presences.flag
    
    bot = Bot(
        command_prefix=PREFIX,
        test_guilds=[
          1098603054397403276, # grey server
        ],
        # **options:
        intents=intents,
        status=disnake.Status.idle,
    )
  except Exception as e:
    print(e)
  else:
    break

# function shared by all Cogs
def setup(bot: commands.Bot):
    module_name = [
      k for k in sys.modules.keys()
      if k.startswith("commands")
    ][-1]
    class_name = module_name.split(".")[-1]
    module = sys.modules.get(module_name)
    
    for name in (
      n for n in dir(module)
      if (
        n.lower() == class_name.lower()
        or n.lower() == f"{class_name.lower()}cog"
      )
      and isinstance(getattr(module, n), type)
    ):
      cog_cls = getattr(module, name)
      break
    cog_obj = cog_cls(bot)
    bot.add_cog(cog_obj)


if __name__ == "__main__":
    # Discover all the commands and load each one
    # into the bot
    path: Path = Path("commands")
    for item in path.iterdir():
        if item.name.endswith(".py"):
            name = f"{item.parent.name}.{item.stem}"
            log.info("Loading extension: %r", name)
            bot.load_extension(name)


_log = logging.getLogger(__name__)


def _cleanup_loop(loop):
    pass

def run(self, *args: Any, **kwargs: Any) -> None:
    loop = self.loop
    try:
        import signal

        loop.add_signal_handler(signal.SIGINT, lambda: loop.stop())
        loop.add_signal_handler(signal.SIGTERM, lambda: loop.stop())
    except:
        pass

    async def runner():
        try:
            await self.start(*args, **kwargs)
        finally:
            if not self.is_closed():
                await self.close()

    def stop_loop_on_completion(f):
        loop.stop()

    future = asyncio.ensure_future(runner(), loop=loop)
    future.add_done_callback(stop_loop_on_completion)
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        _log.info("Received signal to terminate bot and event loop.")
    finally:
        future.remove_done_callback(stop_loop_on_completion)
        _log.info("Cleaning up tasks.")
        _cleanup_loop(loop)
    if not future.cancelled():
        try:
            return future.result()
        except KeyboardInterrupt:
            # I am unsure why this gets raised here
            # but suppress it anyway
            return None


disnake.Client.run = run

class EvtHandler(FileSystemEventHandler):
    def on_any_event(self, evt):
        if evt.event_type == "opened":
            return
        print(f"file event {evt = }")
        for fld, val in inspect.getmembers(evt):
            if not isinstance(val, str):
                continue
            if ".py" not in val:
                continue
            val2 = (
              val.split("/")[-1].split(".py")[0]
            ).split(".")[-1]
            p = Path("commands") / f"{val2}.py"
            if not p.exists():
                continue
            name = ".".join([*p.parent.parts, p.stem])
            log.debug(
              "%s: %s := %r",
              type(evt).__name__, fld, val2
            )
            try:
                bot.reload_extension(name)
                break
            except Exception:
                traceback.print_exc()
            log.info("Reloaded extension: %s", name)


def auto_reload_start(bot):
    evts = []
    obs = Observer()
    h = EvtHandler()
    obs.schedule(
      event_handler=h,
      path=Path.cwd() / "commands",
      recursive=True
    )
    obs.start()


def start_bot():
    thread = current_thread()
    log.info(
        "Starting bot with token '%s%s%s' on thread: %s",
        DISCORD_BOT_TOKEN[:5],
        "*" * len(DISCORD_BOT_TOKEN[5:-5]),
        DISCORD_BOT_TOKEN[-5:],
        thread,
    )
    setattr(bot, "_rollout_all_guilds", True)
    auto_reload_start(bot)
    bot.run(DISCORD_BOT_TOKEN)


loop = get_event_loop_policy().get_event_loop()
# loop.run_until_complete(get_chat(DEFAULT_UID))
Thread(target=start_bot).start()


def iter_over(coro):
    from threading import Event

    it = coro.__aiter__()
    rslts = []
    try:
        while True:
            f = asyncio.run_coroutine_threadsafe(it.__anext__(), loop)
            ev = Event()

            def on_done(_):
                ev.set()

            f.add_done_callback(on_done)
            if ev.wait():
                rslts.append(f.result())
            else:
                break
    except StopAsyncIteration:
        pass
    return rslts


def iter_over_async(ait, loop):
    ait = ait.__aiter__()
    done = False
    from asyncio import Future, ensure_future
    from threading import Event

    async def get_next():
        nonlocal done
        try:
            obj = await ait.__anext__()
            print("got obj=", obj)
            return obj
        except StopAsyncIteration:
            done = True

    while not done:
        if not loop.is_running():
            yield loop.run_until_complete(get_next())
        else:
            event = Event()
            fut = ensure_future(get_next())
            while not fut.done():
                Event().wait(0)
            yield fut.result()
        if done:
            break


def run_coro(coro, loop):
    fut = ensure_future(loop.create_task(coro))
    g = gather(fut)
    sentinel = object()

    def getter():
        while True:
            yield sentinel
            with contextlib.suppress(InvalidStateError):
                yield g.result()
                break
            with contextlib.suppress(InvalidStateError):
                yield g.exception()
                break

    return next(filter(lambda o: o is not sentinel, getter()))


cons = code.InteractiveConsole(locals())
cons.push("import __main__")
cons.push("from __main__ import *")
cons.push("try: import pythonrc")
cons.push("except: pass")
cons.push("")
cons.push("import readline")
cons.push("import rlcompleter")
cons.push("readline.parse_and_bind('tab: complete')")
cons.interact(exitmsg="Goodbye!")