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
    <script src="https://cdn.jsdelivr.net/npm/livekit-client@2/dist/livekit-client.umd.min.js"></script>
    <style>
        body {{ font-family: system-ui, sans-serif; max-width: 640px; margin: 40px auto; padding: 0 20px; }}
        h1 {{ font-size: 1.4em; }}
        #status {{ padding: 12px; border-radius: 8px; background: #f0f0f0; margin: 16px 0; font-weight: 600; }}
        #status.ok {{ background: #dcfce7; }}
        #status.err {{ background: #fee2e2; }}
        .btns {{ display: flex; gap: 12px; margin: 12px 0; }}
        button {{ font-size: 1em; padding: 10px 28px; border-radius: 8px; border: none; cursor: pointer; }}
        #btnConnect {{ background: #2563eb; color: white; }}
        #btnConnect:disabled {{ background: #94a3b8; cursor: not-allowed; }}
        #btnDisconnect {{ background: #dc2626; color: white; display: none; }}
        #log {{ margin-top: 16px; padding: 12px; background: #f8fafc; border: 1px solid #e2e8f0;
                border-radius: 8px; min-height: 120px; white-space: pre-wrap; font-size: 0.85em;
                font-family: monospace; max-height: 400px; overflow-y: auto; }}
    </style>
</head>
<body>
    <h1>Gram Saathi — Voice Test</h1>
    <div id="status">Ready. Click Start Call.</div>
    <div class="btns">
        <button id="btnConnect" onclick="start()">Start Call</button>
        <button id="btnDisconnect" onclick="stop()">End Call</button>
    </div>
    <div id="log"></div>

    <script>
        const LIVEKIT_URL = "{livekit_url}";
        const TOKEN = "{jwt}";
        const ROOM_NAME = "{room_name}";
        let room = null;

        function ts() {{ return new Date().toISOString().substring(11,23); }}
        function log(msg, level) {{
            const el = document.getElementById('log');
            el.textContent += `[${{ts()}}] ${{msg}}\\n`;
            el.scrollTop = el.scrollHeight;
            if (level) console[level](msg);
        }}
        function setStatus(msg, cls) {{
            const el = document.getElementById('status');
            el.textContent = msg;
            el.className = cls || '';
        }}

        async function checkMicPermission() {{
            try {{
                const perm = await navigator.permissions.query({{ name: 'microphone' }});
                log(`mic permission state: ${{perm.state}}`);
                return perm.state;
            }} catch (e) {{
                log(`permissions API not available: ${{e.message}}`);
                return 'unknown';
            }}
        }}

        async function start() {{
            document.getElementById('btnConnect').disabled = true;
            setStatus('Checking microphone permission...');
            log('=== Starting call ===');
            log(`LiveKit URL: ${{LIVEKIT_URL}}`);
            log(`Room: ${{ROOM_NAME}}`);

            const permState = await checkMicPermission();
            if (permState === 'denied') {{
                setStatus('Microphone is blocked. Please allow mic access in browser settings.', 'err');
                log('ERROR: microphone permission denied by browser');
                document.getElementById('btnConnect').disabled = false;
                return;
            }}

            const LK = window.LivekitClient;
            room = new LK.Room({{
                audioCaptureDefaults: {{ autoGainControl: true, noiseSuppression: true, echoCancellation: true }},
                adaptiveStream: true,
                dynacast: true,
            }});

            room.on(LK.RoomEvent.Connected, () => {{
                log(`connected to room, sid=${{room.localParticipant.sid}}`);
            }});

            room.on(LK.RoomEvent.TrackPublished, (pub, participant) => {{
                log(`track published: ${{participant.identity}} kind=${{pub.kind}} source=${{pub.trackInfo?.source}}`);
            }});

            room.on(LK.RoomEvent.LocalTrackPublished, (pub) => {{
                log(`LOCAL track published: kind=${{pub.kind}} trackSid=${{pub.trackSid}}`);
            }});

            room.on(LK.RoomEvent.LocalTrackUnpublished, (pub) => {{
                log(`LOCAL track unpublished: kind=${{pub.kind}}`);
            }});

            room.on(LK.RoomEvent.TrackSubscribed, (track, pub, participant) => {{
                log(`track subscribed from ${{participant.identity}}: kind=${{track.kind}}`);
                if (track.kind === 'audio') {{
                    const el = track.attach();
                    el.autoplay = true;
                    document.body.appendChild(el);
                    log('agent audio attached — you should hear the agent');
                    setStatus('Agent speaking...', 'ok');
                }}
            }});

            room.on(LK.RoomEvent.ParticipantConnected, (p) => {{
                log(`participant joined: ${{p.identity}}`);
                setStatus(`Agent connected: ${{p.identity}}`, 'ok');
            }});

            room.on(LK.RoomEvent.ParticipantDisconnected, (p) => {{
                log(`participant left: ${{p.identity}}`);
            }});

            room.on(LK.RoomEvent.Disconnected, (reason) => {{
                log(`disconnected from room, reason=${{reason}}`);
                setStatus('Disconnected.', '');
                document.getElementById('btnConnect').style.display = '';
                document.getElementById('btnConnect').disabled = false;
                document.getElementById('btnDisconnect').style.display = 'none';
            }});

            room.on(LK.RoomEvent.ConnectionStateChanged, (state) => {{
                log(`connection state: ${{state}}`);
                if (state === 'connected') setStatus('Connected — waiting for agent...', 'ok');
                if (state === 'reconnecting') setStatus('Reconnecting...', '');
            }});

            room.on(LK.RoomEvent.MediaDevicesError, (e) => {{
                log(`MEDIA DEVICES ERROR: ${{e.name}}: ${{e.message}}`);
                setStatus(`Mic error: ${{e.message}}`, 'err');
            }});

            try {{
                setStatus('Connecting to LiveKit...');
                log('calling room.connect...');
                await room.connect(LIVEKIT_URL, TOKEN);
                log('room.connect succeeded');

                setStatus('Requesting microphone...');
                log('calling setMicrophoneEnabled(true)...');
                await room.localParticipant.setMicrophoneEnabled(true);
                const micPub = room.localParticipant.getTrackPublication(LK.Track.Source.Microphone);
                log(`mic track published: ${{micPub ? 'YES sid=' + micPub.trackSid : 'NO — track not found'}}`);

                setStatus('Mic active — speak now', 'ok');
                document.getElementById('btnConnect').style.display = 'none';
                document.getElementById('btnDisconnect').style.display = '';
                log('waiting for agent to join and respond...');
            }} catch (e) {{
                log(`ERROR in start(): ${{e.name}}: ${{e.message}}`);
                setStatus(`Error: ${{e.message}}`, 'err');
                document.getElementById('btnConnect').disabled = false;
            }}
        }}

        async function stop() {{
            log('disconnecting...');
            if (room) {{ await room.disconnect(); room = null; }}
        }}
    </script>
</body>
</html>"""
    return HTMLResponse(content=html)
