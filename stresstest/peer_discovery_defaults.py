import os
import sys
import time
from asyncio import ensure_future, get_event_loop, sleep
from os import chdir, getcwd, mkdir, path
from random import randint

from ipv8.messaging.payload import IntroductionResponsePayload
from ipv8.messaging.payload_headers import GlobalTimeDistributionPayload

# Check if we are running from the root directory
# If not, modify our path so that we can import IPv8
try:
    import ipv8
    del ipv8
except ImportError:
    import __scriptpath__  # noqa: F401


from ipv8.configuration import get_default_configuration  # noqa: I001
from ipv8.types import Community, Peer

from ipv8_service import IPv8, _COMMUNITIES, _WALKERS


START_TIME = time.time()
RESULTS = {}


def custom_intro_response_cb(self: Community,
                             peer: Peer,
                             dist: GlobalTimeDistributionPayload,
                             payload: IntroductionResponsePayload) -> None:
    """
    Wait until we get a non-tracker response.
    Once all overlays have finished, stop the script.
    """
    if (peer.address not in self.network.blacklist) and (self.__class__.__name__ not in RESULTS):
        RESULTS[self.__class__.__name__] = time.time() - START_TIME
        print(self.__class__.__name__, "found a peer!", file=sys.stderr)  # noqa: T201
        if len(get_default_configuration()['overlays']) == len(RESULTS):
            get_event_loop().stop()


async def on_timeout() -> None:
    """
    If it takes longer than 30 seconds to find anything, abort the experiment and set the intro time to -1.0.
    """
    await sleep(30)
    for definition in get_default_configuration()['overlays']:
        if definition['class'] not in RESULTS:
            RESULTS[definition['class']] = -1.0
            print(definition['class'], "found no peers at all!", file=sys.stderr)  # noqa: T201
    get_event_loop().stop()


async def start_communities() -> None:
    """
    Override the Community master peers so we don't interfere with the live network.
    Also hook in our custom logic for introduction responses.
    """
    for community_cls in _COMMUNITIES.values():
        community_cls.community_id = os.urandom(20)
        community_cls.introduction_response_callback = custom_intro_response_cb

    # Create two peers with separate working directories
    previous_workdir = getcwd()
    for i in [1, 2]:
        configuration = get_default_configuration()
        configuration['port'] = 12000 + randint(0, 10000)
        configuration['logger']['level'] = "CRITICAL"
        for overlay in configuration['overlays']:
            overlay['walkers'] = [walker for walker in overlay['walkers'] if walker['strategy'] in _WALKERS]
        workdir = path.abspath(path.join(path.dirname(__file__), str(i)))
        if not path.exists(workdir):
            mkdir(workdir)
        chdir(workdir)
        await IPv8(configuration).start()
        chdir(previous_workdir)

# Actually start running everything, this blocks until the experiment finishes
ensure_future(on_timeout())  # noqa: RUF006
ensure_future(start_communities())  # noqa: RUF006
get_event_loop().run_forever()

# Print the introduction times for all default Communities, sorted alphabetically.
print(','.join(['%.4f' % RESULTS[key] for key in sorted(RESULTS)]))  # noqa: T201
