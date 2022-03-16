import json
import uuid
from distutils.log import WARN
from email.policy import HTTP
from enum import Enum, IntEnum
from logging import DEBUG, WARN, FileHandler, Formatter, StreamHandler, getLogger
from os import path, stat
from time import perf_counter, time
from typing import List, Optional
from urllib import response
from hashlib import sha256

from anyio import current_time
from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import false, text, true
from sqlalchemy.exc import MultipleResultsFound, NoResultFound

from .db import engine

# ロガーオブジェクト
logger = getLogger(__name__)
# ログが複数回表示されるのを防止
logger.propagate = False
# ロガー自体のロギングレベル
logger.setLevel(DEBUG)

# ログをファイルへ
fh = FileHandler("log/debug.log")
fh.setLevel(DEBUG)
fh.setFormatter(
    Formatter(
        "%(asctime)s - %(levelname)s - %(filename)s - %(name)s - %(funcName)s - %(message)s"
    )
)

# WARN以上のログは別で保管する
fh2 = FileHandler("log/warn.log")
fh2.setLevel(WARN)
fh2.setFormatter(
    Formatter(
        "%(asctime)s - %(levelname)s - %(filename)s - %(name)s - %(funcName)s - %(message)s"
    )
)

# ログを標準出力へ
sh = StreamHandler()
sh.setFormatter(Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
sh.setLevel(DEBUG)

# ロガーにハンドラを追加
logger.addHandler(fh)
logger.addHandler(fh2)
logger.addHandler(sh)


# User関連


class LiveDifficulty(Enum):
    normal = 1
    hard = 2


class JoinRoomResult(Enum):
    Ok = 1
    RoomFull = 2
    Disbanded = 3
    OtherError = 4


class WaitRoomStatus(Enum):
    Waiting = 1
    LiveStart = 2
    Dissolution = 3


class RoomUser(BaseModel):
    user_id: int
    name: str
    leader_card_id: int
    select_difficulty: LiveDifficulty
    is_me: bool
    is_host: bool


class InvalidToken(Exception):
    """指定されたtokenが不正だったときに投げる"""


class SafeUser(BaseModel):
    """token を含まないUser"""

    id: int
    name: str
    leader_card_id: int

    class Config:
        orm_mode = True


def create_user(name: str, leader_card_id: int) -> str:
    """Create new user and returns their token"""
    with engine.begin() as conn:
        # トークンが既存のものと衝突しなくなるまでトークンを生成する
        while True:
            token = str(uuid.uuid4())
            hashed_token = sha256(token.encode()).hexdigest()
            result = conn.execute(
                text("SELECT * FROM `user` WHERE `user`.hashed_token=:hashed_token"),
                {"hashed_token": hashed_token},
            ).first()
            if result is None:
                break
        hashed_token = sha256(token.encode()).hexdigest()
        # for _ in range(4):
        #    hashed_token = sha256(hashed_token.encode()).hexdigest()
        logger.info('hashed_token={}'.format(hashed_token))
        _ = conn.execute(
            text(
                "INSERT INTO `user` (name, hashed_token, leader_card_id) VALUES (:name, :hashed_token, :leader_card_id)"
            ),
            {"name": name, "hashed_token": hashed_token, "leader_card_id": leader_card_id},
        )
    return token


def _get_user_by_token(conn, token: str) -> Optional[SafeUser]:
    # start = perf_counter()
    hashed_token = sha256(token.encode()).hexdigest()
    try:
        result = conn.execute(
            text("SELECT * FROM `user` WHERE `hashed_token`=:hashed_token"), dict(hashed_token=hashed_token)
        ).one()
    except NoResultFound:
        logger.exception("User Not Found")
        raise HTTPException(status_code=404)
    except MultipleResultsFound:
        logger.exception("Multiple Users Found")
        raise HTTPException(status_code=500)
    # end = perf_counter()
    # logger.debug("SQL: Time={}".format(end-start))
    return SafeUser.from_orm(result)


def get_user_by_token(token: str) -> Optional[SafeUser]:
    with engine.begin() as conn:
        return _get_user_by_token(conn, token)


def update_user(token: str, name: str, leader_card_id: int) -> None:
    with engine.begin() as conn:
        hashed_token = sha256(token.encode()).hexdigest()
        start = perf_counter()
        _ = conn.execute(
            text(
                "UPDATE `user` SET `name`=:name, `leader_card_id`=:leader_card_id WHERE `hashed_token`=:hashed_token"
            ),
            dict(name=name, hashed_token=hashed_token, leader_card_id=leader_card_id),
        )
        end = perf_counter()
        logger.debug("SQL: Time={}".format(end - start))
    return


# room関連のプログラム


def create_room(token: str, live_id: int, select_difficulty: int) -> int:
    with engine.begin() as conn:
        start = perf_counter()
        response = conn.execute(
            text(
                "INSERT INTO `room` SET `live_id`=:live_id, `joined_user_count`=:joined_user_count, `max_user_count`=:max_user_count, `is_start`=:is_start, `time`=:time"
            ),
            dict(
                live_id=live_id,
                joined_user_count=1,
                max_user_count=4,
                is_start=1,
                time=0,
            ),
        )
        end = perf_counter()
        logger.debug("SQL(INSERT INTO `room`): Time={}".format(end - start))

        user = get_user_by_token(token)

        start = perf_counter()
        _ = conn.execute(
            text(
                "INSERT INTO `room_member` SET `room_id`=:room_id, `user_id`=:user_id, `select_difficulty`=:select_difficulty, `is_host`=:is_host, `judge_miss`=:judge_miss, `judge_bad`=:judge_bad, `judge_good`=:judge_good, `judge_great`=:judge_great, `judge_perfect`=:judge_perfect, `score`=:score"
            ),
            dict(
                room_id=response.lastrowid,
                user_id=user.id,
                select_difficulty=select_difficulty.value,
                is_host=True,
                judge_miss=0,
                judge_bad=0,
                judge_good=0,
                judge_great=0,
                judge_perfect=0,
                score=0,
            ),
        )
        end = perf_counter()
        logger.debug("SQL(INSERT INTO `room_member`): Time={}".format(end - start))
    return response.lastrowid


class RoomList(BaseModel):
    room_id: int
    live_id: int
    joined_user_count: int
    max_user_count: int

    class Config:
        orm_mode = True


def list_room(live_id: int) -> List:
    with engine.begin() as conn:
        if live_id == 0:
            start = perf_counter()
            # live_idが0のときは入室できる全てのライブを取得する
            response = conn.execute(
                text("SELECT * FROM `room` WHERE `is_start`=:is_start"),
                dict(is_start=WaitRoomStatus.Waiting.value),
            )
            end = perf_counter()
            logger.debug("SQL(live_id == 0): Time={}".format(end - start))
        else:
            # 指定したライブIDでかつ入室できるライブを取得する
            start = perf_counter()
            response = conn.execute(
                text(
                    "SELECT * FROM `room` WHERE live_id=:live_id AND `is_start`=:is_start"
                ),
                dict(live_id=live_id, is_start=WaitRoomStatus.Waiting.value),
            )
            end = perf_counter()
            logger.debug("SQL(live_id != 0): Time={}".format(end - start))
    return response.all()


def join_room(
    room_id: int, select_difficulty: LiveDifficulty, user: SafeUser
) -> JoinRoomResult:
    with engine.begin() as conn:
        try:
            start = perf_counter()
            response = conn.execute(
                text(
                    "SELECT `joined_user_count`, `max_user_count`, `is_start` FROM `room` WHERE `room_id`=:room_id FOR UPDATE"
                ),
                dict(room_id=room_id),
            ).one()
            end = perf_counter()
            logger.debug("SQL(SELECT): Time={}".format(end - start))
        except NoResultFound:
            logger.exception("Room Not Found.")
            raise HTTPException(status_code=404)
        except MultipleResultsFound:
            logger.exception("Multi Room Found.")
            raise HTTPException(status_code=500)

        if response.is_start != WaitRoomStatus.Waiting.value:
            return JoinRoomResult.Disbanded
        if response.joined_user_count >= response.max_user_count:
            return JoinRoomResult.RoomFull
        if response.joined_user_count == 0:
            return JoinRoomResult.Disbanded
        if response.joined_user_count < response.max_user_count:
            start = perf_counter()
            _ = conn.execute(
                text(
                    "INSERT INTO `room_member` SET `room_id`=:room_id, `user_id`=:user_id, `select_difficulty`=:select_difficulty, `is_host`=:is_host, `judge_miss`=:judge_miss, `judge_bad`=:judge_bad, `judge_good`=:judge_good, `judge_great`=:judge_great, `judge_perfect`=:judge_perfect, `score`=:score"
                ),
                dict(
                    room_id=room_id,
                    user_id=user.id,
                    select_difficulty=select_difficulty.value,
                    is_host=False,
                    judge_miss=0,
                    judge_bad=0,
                    judge_good=0,
                    judge_great=0,
                    judge_perfect=0,
                    score=0,
                ),
            )
            end = perf_counter()
            logger.debug("SQL(INSERT): Time={}".format(end - start))

            start = perf_counter()
            _ = conn.execute(
                text(
                    "UPDATE `room` SET `joined_user_count`=:joined_user_count WHERE `room_id`=room_id"
                ),
                dict(joined_user_count=response.joined_user_count + 1, room_id=room_id),
            )
            end = perf_counter()
            logger.debug("SQL(UPDATE): Time={}".format(end - start))

            return JoinRoomResult.Ok
    return JoinRoomResult.OtherError


# 戻り値が複数の時のアノテーション
def wait_room(room_id: int, user: SafeUser):
    with engine.begin() as conn:
        start = perf_counter()
        response = conn.execute(
            text("SELECT `is_start` FROM `room` where `room_id`=:room_id"),
            dict(room_id=room_id),
        )
        end = perf_counter()
        logger.debug("SQL(SELECT `is_start`): Time={}".format(end - start))

        start = perf_counter()
        result = conn.execute(
            text(
                "SELECT `room_member`.user_id, `user`.name, `user`.leader_card_id, `room_member`.select_difficulty, `room_member`.is_host FROM `room_member` INNER JOIN `room` ON `room`.room_id = `room_member`.room_id INNER JOIN `user` ON `room_member`.user_id = `user`.id WHERE `room`.room_id=:room_id"
            ),
            dict(room_id=room_id),
        ).all()
        end = perf_counter()
        logger.debug("SQL(SELECT): Time={}".format(end - start))
        if result is None:
            logger.warn('No user in this room, but wait_room is called.')
        resultList = []
        for r in result:
            resultList.append(
                RoomUser(
                    user_id=r.user_id,
                    name=r.name,
                    leader_card_id=r.leader_card_id,
                    select_difficulty=r.select_difficulty,
                    is_me=user.id == r.user_id,
                    is_host=r.is_host,
                )
            )
        try:
            is_start = response.one().is_start
        except (NoResultFound, MultipleResultsFound):
            logger.exception("`is_start` Not Found.")
            raise HTTPException(status_code=500)
        return is_start, resultList


def start_room(room_id: int, user: SafeUser) -> None:
    with engine.begin() as conn:
        try:
            start = perf_counter()
            response = conn.execute(
                text(
                    "SELECT `is_host` FROM `room_member` WHERE `room_id`=:room_id AND `user_id`=:user_id"
                ),
                dict(room_id=room_id, user_id=user.id),
            ).one()[0]
            end = perf_counter()
            logger.debug("SQL(SELECT): Time={}".format(end - start))
        except (NoResultFound, MultipleResultsFound):
            raise HTTPException(status_code=500)
        if response:
            start = perf_counter()
            _ = conn.execute(
                text("UPDATE `room` SET `is_start`=:is_start WHERE `room_id`=:room_id"),
                dict(is_start=WaitRoomStatus.LiveStart.value, room_id=room_id),
            )
            end = perf_counter()
            logger.debug("SQL(UPDATE): Time={}".format(end - start))
        else:
            logger.info("User is not a host.")
            raise HTTPException(status_code=403)


def end_room(
    room_id: int, score: int, user: SafeUser, judge_count_list: list[int]
) -> None:
    while len(judge_count_list) < 5:
        judge_count_list.append(0)
    with engine.begin() as conn:
        current_time = int(time())
        start = perf_counter()
        _ = conn.execute(
            text(
                "UPDATE `room_member` SET `judge_perfect`=:judge_perfect, `judge_great`=:judge_great, `judge_good`=:judge_good, `judge_bad`=:judge_bad, `judge_miss`=:judge_miss, `score`=:score WHERE `user_id`=:user_id AND `room_id`=:room_id"
            ),
            dict(
                judge_perfect=judge_count_list[0],
                judge_great=judge_count_list[1],
                judge_good=judge_count_list[2],
                judge_bad=judge_count_list[3],
                judge_miss=judge_count_list[4],
                score=score,
                user_id=user.id,
                room_id=room_id,
            ),
        )
        end = perf_counter()
        logger.debug("SQL(UPDATE `room_member`): Time={}".format(end - start))

        start = perf_counter()
        _ = conn.execute(
            text(
                "UPDATE `room` SET `time`=CASE WHEN 0 then :new_time ELSE `time` END WHERE room_id=:room_id"
            ),
            dict(
                new_time=current_time,
                room_id=room_id,
            ),
        )
        end = perf_counter()
        logger.debug("SQL(UPDATE `room`): Time={}".format(end - start))


class ResultUser(BaseModel):
    user_id: int
    judge_count_list: list[int]
    score: int


def result_room(room_id: int) -> list[ResultUser]:
    with engine.begin() as conn:
        try:
            start = perf_counter()
            result = conn.execute(
                text(
                    "SELECT `user_id`, `judge_perfect`, `judge_great`, `judge_good`, `judge_bad`, `judge_miss`, `score` FROM `room_member` WHERE `room_id`=:room_id"
                ),
                dict(room_id=room_id),
            )
            end = perf_counter()
            logger.debug("SQL(SELECT FROM `room_member`): Time={}".format(end - start))

            start = perf_counter()
            room_result = conn.execute(
                text("SELECT `is_start`, `time` FROM `room` WHERE `room_id`=:room_id"),
                dict(room_id=room_id),
            ).one()
            end = perf_counter()
            logger.debug("SQL(SELECT FROM `room`): Time={}".format(end - start))

        except (NoResultFound, MultipleResultsFound):
            logger.exception("No Room iss found or Multiple Rooms are found.")
            raise HTTPException(status_code=500)
        resultList = []
        if room_result.is_start != WaitRoomStatus.Waiting.value:
            if result is None:
                logger.warn("result not found, bad /room/result was called")
            for i in result.all():
                if time() - room_result.time < 5 or sum(i[1:6]) == 0:
                    return []
                resultList.append(
                    ResultUser(
                        user_id=i.user_id, judge_count_list=list(i[1:6]), score=i.score
                    )
                )
    return resultList


def leave_room(room_id: int, user: SafeUser) -> None:
    with engine.begin() as conn:
        try:
            # ホストか確認
            start = perf_counter()
            is_host = conn.execute(
                text(
                    "SELECT `is_host` FROM `room_member` WHERE `room_id`=:room_id AND `user_id`=:user_id FOR UPDATE"
                ),
                dict(room_id=room_id, user_id=user.id),
            ).one()[0]
            end = perf_counter()
            logger.debug("SQL(SELECT `is_host`): Time={}".format(end - start))
        except (NoResultFound, MultipleResultsFound):
            logger.exception("No Room is found or Multiple Rooms are found.")
            raise HTTPException(status_code=500)
        if is_host:
            # 他にメンバーがいるか確認
            start = perf_counter()
            result = conn.execute(
                text("SELECT `user_id` FROM `room_member` WHERE `room_id`=:room_id"),
                dict(room_id=room_id),
            )
            end = perf_counter()
            logger.debug("SQL(SELECT `is_host`): Time={}".format(end - start))
            for i in result.all():
                # 他にメンバーがいる時
                if i[0] != user.id:
                    start = perf_counter()
                    _ = conn.execute(
                        text(
                            "UPDATE `room_member` SET `is_host`=:is_host WHERE `user_id`=:user_id AND `room_id`=:room_id"
                        ),
                        dict(is_host=True, user_id=i[0], room_id=room_id),
                    )
                    end = perf_counter()
                    logger.debug("SQL(SELECT `is_host`): Time={}".format(end - start))
                    try:
                        start = perf_counter()
                        joined_user_count = conn.execute(
                            text(
                                "SELECT `joined_user_count` FROM `room` WHERE `room_id`=:room_id"
                            ),
                            dict(room_id=room_id),
                        ).one()
                        end = perf_counter()
                        logger.debug(
                            "SQL(SELECT `joined_user_count`): Time={}".format(
                                end - start
                            )
                        )
                    except NoResultFound:
                        logger.exception("Room Not Found.")
                        raise HTTPException(status_code=404)
                    except MultipleResultsFound:
                        logger.exception("Multiple Room is Found.")
                        raise HTTPException(status_code=500)
                    start = perf_counter()
                    _ = conn.execute(
                        text(
                            "UPDATE `room` SET `joined_user_count`=:joined_user_count WHERE `room_id`=:room_id"
                        ),
                        dict(
                            joined_user_count=joined_user_count[0] - 1, room_id=room_id
                        ),
                    )
                    end = perf_counter()
                    logger.debug("SQL(UPDATE `room`): Time={}".format(end - start))

                    start = perf_counter()
                    _ = conn.execute(
                        text(
                            "DELETE FROM `room_member` WHERE `user_id`=:user_id AND `room_id`=:room_id"
                        ),
                        dict(user_id=user.id, room_id=room_id),
                    )
                    end = perf_counter()
                    logger.debug(
                        "SQL(DELETE `room_member`): Time={}".format(end - start)
                    )
                    return
            # 他にメンバーがいない時
            # ルームを解散する
            start = perf_counter()
            _ = conn.execute(
                text(
                    "UPDATE `room` SET `is_start`=:is_start, `joined_user_count`=:joined_user_count WHERE `room_id`=:room_id"
                ),
                dict(
                    is_start=WaitRoomStatus.Dissolution.value,
                    joined_user_count=0,
                    room_id=room_id,
                ),
            )
            end = perf_counter()
            logger.debug("SQL(UPDATE `room`): Time={}".format(end - start))
        else:
            start = perf_counter()
            _ = conn.execute(
                text(
                    "UPDATE `room` SET `joined_user_count`=`joined_user_count`-1 WHERE `room_id`=:room_id"
                ),
                dict(room_id=room_id),
            )
            end = perf_counter()
            logger.debug("SQL(UPDATE `room`): Time={}".format(end - start))

            start = perf_counter()
            _ = conn.execute(
                text(
                    "DELETE FROM `room_member` WHERE `user_id`=:user_id AND `room_id`=:room_id"
                ),
                dict(user_id=user.id, room_id=room_id),
            )
            end = perf_counter()
            logger.debug("SQL(DELETE `room_member`): Time={}".format(end - start))
