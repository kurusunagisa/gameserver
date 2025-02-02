import json
from calendar import c
from enum import Enum

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from . import model
from .model import SafeUser

import datetime


# from lib2to3.pytree import Base

app = FastAPI()

# Sample APIs


@app.get("/")
async def root():
    """ルートディレクトリ"""
    return {"message": "Hello World"}


# User APIs


class UserCreateRequest(BaseModel):
    """UserCreateのリクエストのスキーマ定義"""

    user_name: str
    leader_card_id: int


class UserCreateResponse(BaseModel):
    """UserCreateのレスポンスのスキーマ定義"""

    user_token: str


@app.post("/user/create", response_model=UserCreateResponse)
def user_create(req: UserCreateRequest):
    """新規ユーザー作成"""
    model.logger.info("Called /user/create")
    token = model.create_user(req.user_name, req.leader_card_id)
    return UserCreateResponse(user_token=token)


bearer = HTTPBearer()


def get_auth_token(cred: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    """トークンの取得"""
    assert cred is not None
    if not cred.credentials:
        raise HTTPException(status_code=401, detail="invalid credential")
    return cred.credentials


@app.get("/user/me", response_model=SafeUser)
def user_me(token: str = Depends(get_auth_token)):
    model.logger.info("Called /user./me")
    """トークンから自身の情報を取得"""
    user = model.get_user_by_token(token)
    if user is None:
        raise HTTPException(status_code=404)
    return user


class Empty(BaseModel):
    """空のスキーマ定義"""

    pass


@app.post("/user/update", response_model=Empty)
def update(req: UserCreateRequest, token: str = Depends(get_auth_token)):
    """Update user attributes"""
    model.logger.info("Called /user/update")
    model.update_user(token, req.user_name, req.leader_card_id)
    return {}


"""
room関連のプログラム
"""


class RoomCreateRequest(BaseModel):
    """RoomCreateのリクエストのスキーマ定義"""

    live_id: int
    select_difficulty: model.LiveDifficulty


class RoomCreateResponse(BaseModel):
    """RoomCreateのレスポンスのスキーマ定義"""

    room_id: int


@app.post("/room/create", response_model=RoomCreateResponse)
def room_create(req: RoomCreateRequest, token: str = Depends(get_auth_token)):
    """新規のルーム作成"""
    model.logger.info("Called /room/create")
    id = model.create_room(token, req.live_id, req.select_difficulty)
    return RoomCreateResponse(room_id=id)


class RoomListRequest(BaseModel):
    """RoomListのリクエストのスキーマ定義"""

    live_id: int


class RoomListResponse(BaseModel):
    """RoomListのレスポンスのスキーマ定義"""

    room_info_list: list


class RoomInfo(BaseModel):
    """
    RoomInfo構造体の定義
    room_id: ルームのid
    live_id: 楽曲id
    joined_user_count: 参加している人数のカウント
    max_user_count: 参加人数上限
    """

    room_id: int
    live_id: int
    joined_user_count: int
    max_user_count: int


@app.post("/room/list", response_model=RoomListResponse)
def room_list(req: RoomListRequest):
    """入れるルームのリストの取得"""
    model.logger.info("Called /room/list")
    results = model.list_room(req.live_id)
    response = []
    for result in results:
        response.append(
            RoomInfo(
                room_id=result.room_id,
                live_id=result.live_id,
                joined_user_count=result.joined_user_count,
                max_user_count=result.max_user_count,
            )
        )
    return RoomListResponse(room_info_list=response)


class RoomJoinRequest(BaseModel):
    """RoomJoinのリクエストのスキーマ定義"""

    room_id: int
    select_difficulty: model.LiveDifficulty


class RoomJoinResponse(BaseModel):
    """RoomJoinのレスポンスのスキーマ定義"""

    join_room_result: model.JoinRoomResult


@app.post("/room/join", response_model=RoomJoinResponse)
def room_join(req: RoomJoinRequest, token: str = Depends(get_auth_token)):
    """ルームへの入室を行う"""
    model.logger.info("Called /room/join")
    user = model.get_user_by_token(token)
    if user is None:
        raise HTTPException(status_code=404)
    response = model.join_room(
        room_id=req.room_id, select_difficulty=req.select_difficulty, user=user
    )
    return RoomJoinResponse(join_room_result=response)


class RoomWaitRequest(BaseModel):
    room_id: int


class RoomWaitResponse(BaseModel):
    status: model.WaitRoomStatus
    room_user_list: list[model.RoomUser]


@app.post("/room/wait", response_model=RoomWaitResponse)
def room_wait(req: RoomWaitRequest, token: str = Depends(get_auth_token)):
    """ルーム待機中"""
    user = model.get_user_by_token(token)
    if user is None:
        raise HTTPException(status_code=404)
    response = model.wait_room(room_id=req.room_id, user=user)
    return RoomWaitResponse(status=response[0], room_user_list=response[1])


class RoomStartRequest(BaseModel):
    room_id: int


@app.post("/room/start", response_model=Empty)
def room_start(req: RoomStartRequest, token: str = Depends(get_auth_token)):
    """ライブ開始"""
    model.logger.info("Called /room/start")
    user = model.get_user_by_token(token)
    if user is None:
        raise HTTPException(status_code=404)
    _ = model.start_room(room_id=req.room_id, user=user)
    return {}


class RoomEndRequest(BaseModel):
    room_id: int
    judge_count_list: list[int]
    score: int


@app.post("/room/end", response_model=Empty)
def room_end(req: RoomEndRequest, token: str = Depends(get_auth_token)):
    """ライブ終了時"""
    model.logger.info("Called /room/end")
    user = model.get_user_by_token(token)
    if user is None:
        raise HTTPException(status_code=404)
    _ = model.end_room(
        room_id=req.room_id,
        judge_count_list=req.judge_count_list,
        score=req.score,
        user=user,
    )
    return {}


class RoomResultRequest(BaseModel):
    room_id: int


class RoomResultResponse(BaseModel):
    result_user_list: list[model.ResultUser]


@app.post("/room/result", response_model=RoomResultResponse)
def room_result(req: RoomResultRequest):
    """ライブのリザルト"""
    model.logger.info("Called /room/result")
    result = model.result_room(room_id=req.room_id)
    return RoomResultResponse(result_user_list=result)


class RoomLeaveRequest(BaseModel):
    room_id: int


@app.post("/room/leave", response_model=Empty)
def room_leave(req: RoomLeaveRequest, token: str = Depends(get_auth_token)):
    """ライブの待機画面からの退出"""
    model.logger.info("Called /room/leave")
    user = model.get_user_by_token(token)
    if user is None:
        raise HTTPException(status_code=404)
    _ = model.leave_room(room_id=req.room_id, user=user)
    return {}
