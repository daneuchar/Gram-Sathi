"""Test endpoint — generates a LiveKit token and serves a browser-based voice test page."""
import logging
import time

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from livekit.api import AccessToken, VideoGrants, LiveKitAPI, CreateRoomRequest, RoomAgentDispatch

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["test"])


def _room_name() -> str:
    return f"gram-saathi-test-{int(time.time())}"


def _create_token(room_name: str, identity: str = "web-tester", phone: str = "+910000000000") -> str:
    """Generate a LiveKit access token for the test room."""
    token = AccessToken(
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    )
    token.with_identity(identity)
    token.with_name("Web Tester")
    token.with_metadata(phone)
    token.with_grants(VideoGrants(
        room_join=True,
        room=room_name,
        can_publish=True,
        can_subscribe=True,
    ))
    return token.to_jwt()


@router.get("/test")
async def test_page():
    """Serve a minimal voice test page using LiveKit JS SDK."""
    livekit_url = settings.livekit_public_url or settings.livekit_url or "ws://localhost:7880"
    room_name = _room_name()

    # Pre-create the room with agent dispatch so the worker picks up the job
    async with LiveKitAPI(
        url=livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    ) as api:
        await api.room.create_room(CreateRoomRequest(
            name=room_name,
            empty_timeout=300,
            metadata="+910000000000",
            agents=[RoomAgentDispatch(agent_name="")],
        ))
    logger.info("Created test room %s with agent dispatch", room_name)

    jwt = _create_token(room_name)

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Gram Saathi — Voice Test</title>
    <script src="https://cdn.jsdelivr.net/npm/livekit-client/dist/livekit-client.umd.js"></script>
    <style>
        body {{ font-family: system-ui, sans-serif; max-width: 600px; margin: 60px auto; padding: 0 20px; }}
        h1 {{ font-size: 1.4em; }}
        #status {{ padding: 12px; border-radius: 8px; background: #f0f0f0; margin: 20px 0; }}
        button {{ font-size: 1.1em; padding: 12px 32px; border-radius: 8px; border: none; cursor: pointer; }}
        #connect {{ background: #2563eb; color: white; }}
        #connect:disabled {{ background: #94a3b8; cursor: not-allowed; }}
        #disconnect {{ background: #dc2626; color: white; display: none; }}
        #transcript {{ margin-top: 20px; padding: 12px; background: #f8fafc; border: 1px solid #e2e8f0;
                       border-radius: 8px; min-height: 100px; white-space: pre-wrap; font-size: 0.95em; }}
    </style>
</head>
<body>
    <h1>Gram Saathi — Voice Test</h1>
    <div id="status">Ready to connect.</div>
    <button id="connect" onclick="start()">Start Call</button>
    <button id="disconnect" onclick="stop()">End Call</button>
    <div id="transcript"></div>

    <script>
        const url = "{livekit_url}";
        const token = "{jwt}";
        let room = null;

        function log(msg) {{
            document.getElementById('transcript').textContent += msg + '\\n';
        }}

        function setStatus(msg) {{
            document.getElementById('status').textContent = msg;
        }}

        async function start() {{
            const LivekitClient = window.LivekitClient;
            room = new LivekitClient.Room({{
                audioCaptureDefaults: {{ autoGainControl: true, noiseSuppression: true }},
            }});

            room.on(LivekitClient.RoomEvent.TrackSubscribed, (track) => {{
                if (track.kind === 'audio') {{
                    const el = track.attach();
                    document.body.appendChild(el);
                    log('[agent audio connected]');
                }}
            }});

            room.on(LivekitClient.RoomEvent.ParticipantConnected, (participant) => {{
                log('[agent joined: ' + participant.identity + ']');
            }});

            room.on(LivekitClient.RoomEvent.Disconnected, () => {{
                setStatus('Disconnected.');
                document.getElementById('connect').style.display = '';
                document.getElementById('connect').disabled = false;
                document.getElementById('disconnect').style.display = 'none';
            }});

            try {{
                setStatus('Connecting...');
                document.getElementById('connect').disabled = true;
                await room.connect(url, token);
                await room.localParticipant.setMicrophoneEnabled(true);
                setStatus('Connected — waiting for agent...');
                document.getElementById('connect').style.display = 'none';
                document.getElementById('disconnect').style.display = '';
                log('[connected to room: {room_name}]');
                log('[mic enabled — waiting for agent to join...]');
            }} catch (e) {{
                setStatus('Connection failed: ' + e.message);
                document.getElementById('connect').disabled = false;
                log('[error] ' + e.message);
            }}
        }}

        async function stop() {{
            if (room) {{
                await room.disconnect();
                room = null;
            }}
        }}
    </script>
</body>
</html>"""
    return HTMLResponse(content=html)
