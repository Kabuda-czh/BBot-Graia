import asyncio

from loguru import logger
from graia.saya import Channel
from graia.ariadne.app import Ariadne
from graia.ariadne.model import MemberPerm
from graia.ariadne.exception import UnknownTarget
from graia.ariadne.message.chain import MessageChain
from graia.ariadne.connection.util import UploadMethod
from graia.ariadne.message.element import Image, AtAll
from graia.scheduler.saya.schema import SchedulerSchema
from graia.scheduler.timers import every_custom_seconds

from core import BOT_Status
from core.bot_config import BotConfig
from library.grpc import grpc_dynall_get
from library.text2image import text2image
from data import insert_dynamic_push, is_dyn_pushed
from library.dynamic_shot import get_dynamic_screenshot
from library.bilibili_request import relation_modify, dynamic_like
from library import get_subid_list, get_group_sublist, set_name, unsubscribe_uid
from library.grpc.bilibili.app.dynamic.v2.dynamic_pb2 import DynamicType, DynModuleType

channel = Channel.current()


@channel.use(SchedulerSchema(every_custom_seconds(3)))
async def main(app: Ariadne):

    if not BOT_Status["init"]:
        return
    elif len(get_subid_list()) == 0:
        return

    BOT_Status["updateing"] = True
    sub_list = get_subid_list().copy()

    # 动态更新检测
    # 获取当前登录账号的动态列表
    logger.debug("[Dynamic] Start to get dynamic list")
    for _ in range(3):
        try:
            dynall = await asyncio.wait_for(grpc_dynall_get(), timeout=10)
            break
        except asyncio.TimeoutError:
            logger.debug("[Dynamic] Get dynamic list failed, retry")
            continue
    else:
        logger.debug("[Dynamic] Get dynamic list failed")
        BOT_Status["updateing"] = False

    logger.debug(f"[Dynamic] Get {len(dynall)} dynamics")
    if dynall:
        logger.debug("[Dynamic] Start to check dynamic")
        for dyn in dynall:
            up_id = str(dyn.modules[0].module_author.author.mid)
            up_name = dyn.modules[0].module_author.author.name
            dynid = dyn.extend.dyn_id_str
            dyn_desc = " ".join(
                [
                    x.module_desc.text
                    for x in dyn.modules
                    if x.module_type == DynModuleType.module_desc
                ]
            )

            logger.debug(f"[Dynamic] Check dynamic {dynid}, {up_name}({up_id})")

            try:
                if (
                    int(dynid) <= BOT_Status["offset"]
                    or up_id in BOT_Status["skip_uid"]
                    or is_dyn_pushed(dynid)
                ):
                    continue
            except ValueError:
                continue

            logger.debug(f"[Dynamic] Start to push dynamic {dynid}")
            if up_id in sub_list:
                logger.info(
                    f"[BiliBili推送] {dynid} | {up_name} 更新了动态，共有 {len(sub_list[up_id])} 个群订阅了该 UP"
                )
                try:
                    shot_image = await get_dynamic_screenshot(dynid)
                    dyn_img = await app.upload_image(shot_image, UploadMethod.Group)
                except Exception as e:
                    err_msg = f"[BiliBili推送] {dynid} | {up_name} 更新了动态，截图失败"
                    logger.error(err_msg)
                    logger.exception(e)
                    BOT_Status["updateing"] = False
                    return await app.send_friend_message(
                        BotConfig.master,
                        MessageChain(
                            Image(data_bytes=await text2image(f"{err_msg}\n{e}"))
                        ),
                    )

                if set_name(up_id, up_name):
                    logger.debug(f"[Dynamic] Set {up_id} name to {up_name}")
                else:
                    logger.debug(f"[Dynamic] Can't set {up_id} name to {up_name}")

                if dyn.card_type == DynamicType.forward:
                    type_text = "转发了一条动态！"
                elif dyn.card_type == DynamicType.word:
                    type_text = "发布了一条文字动态！"
                elif dyn.card_type == DynamicType.draw:
                    type_text = "发布了一条图文动态！"
                elif dyn.card_type == DynamicType.article:
                    type_text = "发布了一条专栏！"
                elif dyn.card_type == DynamicType.av:
                    type_text = "发布了一条新视频！"
                else:
                    type_text = "发布了一条动态！"

                await app.send_friend_message(
                    BotConfig.master,
                    MessageChain(
                        f"UP {up_name}（{up_id}）{type_text}\n",
                        dyn_img,
                        f"\nhttps://t.bilibili.com/{dynid}",
                    ),
                )

                for groupid, data in sub_list[up_id].items():
                    if BotConfig.Debug.enable and groupid not in BotConfig.Debug.groups:
                        continue
                    if data["send"]["dynamic"]:
                        nick = (
                            f"*{up_nick} "
                            if (up_nick := data["nick"])
                            else f"UP {up_name}（{up_id}）"
                        )
                        msg = [
                            f"本群订阅的 {nick}{type_text}\n",
                            dyn_img,
                            f"\nhttps://t.bilibili.com/{dynid}",
                        ]
                        if data["atall"]:
                            bot_perm = (await app.get_group(int(groupid))).account_perm

                            if bot_perm in [
                                MemberPerm.Administrator,
                                MemberPerm.Owner,
                            ]:
                                msg = [AtAll(), " "] + msg
                            # else:
                            #     msg = ["@全体成员 "] + msg
                        try:
                            await app.send_group_message(
                                groupid,
                                MessageChain(msg),
                            )
                            await asyncio.sleep(1)
                        except UnknownTarget:
                            remove_list = []
                            logger.warning(
                                f"[BiliBili推送] {dynid} | 推送失败，找不到该群 {groupid}，已删除该群订阅的 {len(remove_list)} 个 UP"
                            )
                            for subid, _, _ in get_group_sublist(groupid):
                                await unsubscribe_uid(subid, groupid)
                                remove_list.append(subid)
                        except Exception as e:
                            logger.error(f"[BiliBili推送] {dynid} | 推送失败，未知错误")
                            logger.exception(e)
                like = await dynamic_like(dynid)
                if like["code"] == 0:
                    logger.info(f"[BiliBili推送] {dynid} | 动态点赞成功")
                else:
                    logger.error(f"[BiliBili推送] {dynid} | 动态点赞失败：{like}")
                insert_dynamic_push(
                    up_id,
                    up_name,
                    dynid,
                    dyn.card_type,
                    dyn_desc,
                    len(sub_list[up_id]),
                )
            else:
                logger.warning(
                    f"[BiliBili推送] {dynid} | 没有找到订阅 UP {up_name}（{up_id}）的群，已退订！"
                )
                resp = await relation_modify(up_id, 2)
                if resp["code"] == 0:
                    logger.info("[BiliBili推送] 退订成功！")
                    msg = "已被退订！"
                else:
                    logger.error(f"[BiliBili推送] {dynid} | 退订失败：{resp}")
                    msg = f"退订失败：{resp}"
                await app.send_friend_message(
                    BotConfig.master,
                    MessageChain(
                        f"[BiliBili推送] {dynid} | 未找到订阅 {up_name}（{up_id}）的群，{msg}",
                    ),
                )

        if BOT_Status["skip"]:
            BOT_Status["skip"] -= 1
            if not BOT_Status["skip"]:
                BOT_Status["skip_uid"] = []

        # 将当前检测到的第一条动态 id 设置为最新的动态 id
        if BOT_Status["offset"] > int(dynall[-1].extend.dyn_id_str):
            logger.info("[BiliBili推送] 有 UP 删除了动态")
        BOT_Status["offset"] = int(dynall[-1].extend.dyn_id_str)
    else:
        logger.debug(dynall)
    BOT_Status["updateing"] = False
    logger.debug("[Dynamic] Updateing finished")


@channel.use(SchedulerSchema(every_custom_seconds(2)))
async def debug():
    logger.debug(BOT_Status)
