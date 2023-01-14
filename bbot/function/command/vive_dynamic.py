from graia.saya import Channel
from graia.ariadne.app import Ariadne
from graia.ariadne.model import Group
from sentry_sdk import capture_exception
from graia.ariadne.message.chain import MessageChain
from graia.ariadne.event.message import GroupMessage
from graia.ariadne.message.element import Image, Source
from bilireq.grpc.dynamic import grpc_get_user_dynamics
from graia.saya.builtins.broadcast.schema import ListenerSchema
from graia.ariadne.message.parser.twilight import (
    Twilight,
    FullMatch,
    RegexResult,
    ArgumentMatch,
    WildcardMatch,
)

from ...utils.uid_extract import uid_extract
from ...core.control import Interval, Permission
from ...utils.bilibili_request import get_b23_url
from ...utils.dynamic_shot import get_dynamic_screenshot

channel = Channel.current()


@channel.use(
    ListenerSchema(
        listening_events=[GroupMessage],
        inline_dispatchers=[
            Twilight(
                [
                    FullMatch("查看动态"),
                    "test" @ ArgumentMatch("--test", action="store_true", optional=True),
                    "anything" @ WildcardMatch(),
                ]
            )
        ],
        decorators=[Permission.require(), Interval.require()],
    )
)
async def main(
    app: Ariadne,
    group: Group,
    source: Source,
    anything: RegexResult,
):

    if not (uid := await uid_extract(anything.result.display, group.id)):
        return await app.send_group_message(
            group,
            MessageChain("未找到该 UP，请输入正确的 UP 群内昵称、UP 名、UP UID或 UP 首页链接"),
            quote=source,
        )

    if int(uid) == 0:
        return await app.send_group_message(group, MessageChain("UP 主不存在"), quote=source)

    try:
        res = await grpc_get_user_dynamics(int(uid))
    except Exception as e:
        capture_exception(e)
        return await app.send_group_message(group, MessageChain(f"获取动态失败：{e}"), quote=source)

    if res.list:
        if len(res.list) > 1:
            if res.list[0].modules[0].module_author.is_top:
                dyn = res.list[1]
            else:
                dyn = res.list[0]
        else:
            dyn = res.list[0]
        shot_image = await get_dynamic_screenshot(dyn)
        return await app.send_group_message(
            group,
            MessageChain(
                Image(data_bytes=shot_image),
                "\n",
                await get_b23_url(f"https://t.bilibili.com/{dyn.extend.dyn_id_str}"),
            ),
            quote=source,
        )
    await app.send_group_message(group, MessageChain("该 UP 未发布任何动态"), quote=source)
