from contextlib import asynccontextmanager
import asyncio
import os
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from did_core.scenarios import SCENARIOS
from .runtime import RosRuntime, DEFAULT_SESSION

class Session(BaseModel):
    model_config=ConfigDict(extra='forbid')
    scenario:Literal['easy','medium','hard']
    seed:int=Field(strict=True,ge=0,le=2147483647)
    mode:Literal['baseline','adaptive']
    planner_mode:Literal['algorithmic','llm']='algorithmic'
class CommandRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    command:Literal['pause','resume','return','stop']

@asynccontextmanager
async def lifespan(app):
    runtime=RosRuntime();app.state.runtime=runtime
    if os.environ.get('DID_RUNTIME')=='ros':await runtime.open()
    else:runtime.cache.error='ROS runtime unavailable in this environment'
    try:yield
    finally:await runtime.close()

app=FastAPI(title='DID LAB API',lifespan=lifespan)
def runtime():
    if not hasattr(app.state,'runtime'):
        app.state.runtime=RosRuntime();app.state.runtime.cache.error='ROS runtime unavailable'
    return app.state.runtime
@app.get('/api/health')
def health():return {'status':'ok'}
@app.get('/api/scenarios')
def scenarios():return SCENARIOS
@app.get('/api/state')
def state():return runtime().snapshot()['state']
@app.get('/api/journal')
def journal():return runtime().snapshot()['journal']
@app.get('/api/trajectory')
def trajectory():return runtime().snapshot()['trajectory']
@app.get('/api/map')
def map_data():
    with runtime().cache.lock:
        value=runtime().cache.map
        if value is None:raise HTTPException(503,'ROS map unavailable')
        return value
async def execute(fn,*args):
    try:
        async with runtime().operation_lock:return await fn(*args)
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc
    except RuntimeError as exc:raise HTTPException(503,str(exc)) from exc
    except asyncio.TimeoutError as exc:raise HTTPException(504,'Runtime operation timed out') from exc
@app.post('/api/missions',status_code=201)
async def start(body:Session):return (await execute(runtime().start,body.model_dump()))['state']
@app.post('/api/missions/reset')
async def reset(body:Session):return (await execute(runtime().reset,body.model_dump()))['state']
@app.post('/api/missions/command')
@app.post('/api/command')
async def command(body:CommandRequest):
    allowed={'pause':('running','returning'),'resume':('paused',),'return':('running','paused','returning'),'stop':('running','paused','returning')}
    if runtime().snapshot()['state']['status'] not in allowed[body.command]:raise HTTPException(409,'Command unavailable in current state')
    return (await execute(runtime().command,body.command))['state']
@app.websocket('/api/telemetry')
async def telemetry(ws:WebSocket):
    await ws.accept()
    try:
        while True:
            await ws.send_json(runtime().snapshot());await asyncio.sleep(.25)
    except (WebSocketDisconnect,RuntimeError):pass

frontend=Path(__file__).resolve().parents[2]/'frontend/dist'
if frontend.is_dir():app.mount('/',StaticFiles(directory=frontend,html=True),name='frontend')
def run():
    import uvicorn
    uvicorn.run('did_backend.main:app',host=os.environ.get('DID_HOST','127.0.0.1'),port=8000)
if __name__=='__main__':run()
