from __future__ import annotations
import asyncio
import logging
from dotenv import load_dotenv
import json
import os
from time import perf_counter
from typing import Annotated
from livekit import rtc, api
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    llm,
)
from livekit.agents.multimodal import MultimodalAgent
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import deepgram, openai, silero, elevenlabs
from livekit.plugins.elevenlabs import tts
import asyncio
from livekit import rtc, api
from livekit.agents import llm
import logging
from livekit.plugins.deepgram import STT
from livekit.agents import transcription, stt  # Ensure these imports are correct
from livekit.agents import stt, transcription
from livekit.plugins.deepgram import STT
import aiohttp
import logging

# Set the log level for livekit.agents and asyncio
logging.getLogger('livekit.agents').setLevel(logging.WARNING)  # Set to WARNING to filter out INFO and DEBUG logs
logging.getLogger('asyncio').setLevel(logging.WARNING)  # Filter out asyncio logs

# load environment variables, this is optional, only used for local development
load_dotenv(dotenv_path=".env.local")
logger = logging.getLogger("outbound-caller")
logger.setLevel(logging.INFO)

outbound_trunk_id = os.getenv("SIP_OUTBOUND_TRUNK_ID")
_default_instructions = (
    "You are a scheduling assistant for a dental practice. Your interface with user will be voice."
    "You will be on a call with a patient who has an upcoming appointment. Your goal is to confirm the appointment details."
    "As a customer service representative, you will be polite and professional at all times. Allow user to end the conversation."
)

DEEPSEEK_API_KEY = "sk-8f3c9b094df34051a1aefbc413f03f80"

import aiohttp  # ✅ Ensure aiohttp is imported

import aiohttp
import asyncio

import aiohttp
import asyncio
from livekit.agents import stt, transcription
from livekit.plugins.deepgram import STT

# Reset TTS session
async def reset_tts_session():
    global eleven_tts
    eleven_tts.session = None  # Force reinitialization

# Main entrypoint function to handle job context
async def entrypoint(ctx: JobContext):
    global _default_instructions, outbound_trunk_id
   

    logger.info(f"🔄 Starting new session for room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    user_identity = "phone_user"
    phone_number = ctx.job.metadata

    if not phone_number:
        logger.error("❌ No phone number found in metadata!")
        return

    logger.info(f"📞 Dialing {phone_number} in room {ctx.room.name}")

    # ✅ Run `capture_transcripts(ctx)` as a background task



    # Reset ElevenLabs session (important for avoiding "Session is closed" errors)
    await reset_tts_session()

    try:
        await ctx.api.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                room_name=ctx.room.name,
                sip_trunk_id=outbound_trunk_id,
                sip_call_to=phone_number,
                participant_identity=user_identity,
            )
        )
        logger.info("✅ SIP Call initiated successfully")
    except Exception as e:
        logger.error(f"❌ Failed to start SIP call: {e}")
        return

    participant = await ctx.wait_for_participant(identity=user_identity)

    # Look up appointment details
    instructions = (
        _default_instructions
        + "The customer's name is Jayden. His appointment is next Tuesday at 3pm."
    )

    # Start the voice agent
    run_voice_pipeline_agent(ctx, participant, instructions)

    # Capture transcription (setup for audio stream)
    async def capture_transcription_for_audio_track(track):
        audio_stream = rtc.AudioStream(track)  # Get the audio stream from the track
        stt_stream = STT().stream()  # Initialize the STT stream (Deepgram in this case)
   
    start_time = perf_counter()
    while True:
        call_status = participant.attributes
        if participant.disconnect_reason:
            logger.info(f"❌ Call ended: {participant.disconnect_reason}")
            break
        # Optionally log periodic status updates if needed
        await asyncio.sleep(1)

    # Once the call ends, clean up the session
    await cleanup_session(ctx)






async def cleanup_session(ctx: JobContext):
    """Ends session, cleans up, and sends transcript to webhook."""
    logger.info("🛑 Ending session and cleaning up")

    try:
        api_client = api.LiveKitAPI(
            os.getenv("LIVEKIT_URL"),
            os.getenv("LIVEKIT_API_KEY"),
            os.getenv("LIVEKIT_API_SECRET"),
        )

        room_name = ctx.room.name

        # ✅ Remove participants before deleting room
        participants = await api_client.room.list_participants(api.ListParticipantsRequest(room=room_name))
        for participant in participants.participants:
            await api_client.room.remove_participant(api.RoomParticipantIdentity(
                room=room_name,
                identity=participant.identity
            ))
            logger.info(f"✅ Removed participant: {participant.identity}")

        # ✅ Double-check if room is empty before deletion
        participants = await api_client.room.list_participants(api.ListParticipantsRequest(room=room_name))
        if not participants.participants:
            await api_client.room.delete_room(api.DeleteRoomRequest(room=room_name))
            logger.info(f"✅ Room {room_name} successfully deleted")
        else:
            logger.error(f"❌ Room {room_name} still has participants after attempted removal!")

    except Exception as e:
        logger.error(f"❌ Room deletion failed: {e}")

    # ✅ Ensure ElevenLabs session is reset
    await reset_tts_session()
    logger.info("✅ ElevenLabs session reset")

    # ✅ Capture final transcript and send it to webhook
  
    phone_number = ctx.job.metadata  # Ensure phone number is stored in metadata

  

    # ✅ Disconnect the agent properly
    ctx.shutdown(reason="Session is going to be sdflkdsflsd ended")




def run_voice_pipeline_agent(
    ctx: JobContext, participant: rtc.RemoteParticipant, instructions: str
):
    logger.info("🎙️ Starting voice pipeline agent")

    # Initialize LLM and context for the agent
    initial_ctx = llm.ChatContext().append(
        role="system",
        text=instructions,
    )

    # Initialize the agent with all components
    agent = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(model="nova-2-phonecall"),  # Deepgram STT integration
        llm=openai.LLM.with_deepseek(model="deepseek-chat", temperature=0.7, api_key=DEEPSEEK_API_KEY),
        tts=eleven_tts,
        chat_ctx=initial_ctx,
        fnc_ctx=CallActions(api=ctx.api, participant=participant, room=ctx.room),
    )

    # ✅ Capture user transcription directly from Deepgram
    logger.info(f"🔄 This is agent pipline Session =======>>>> ############################## <<< KLJFLDJ {ctx.room.name}")


    # Start the agent with the participant (this actually triggers the agent's work)
    agent.start(ctx.room, participant)




class CallActions(llm.FunctionContext):
    """
    Detect user intent and perform actions
    """

    def __init__(
        self, *, api: api.LiveKitAPI, participant: rtc.RemoteParticipant, room: rtc.Room
    ):
        super().__init__()

        self.api = api
        self.participant = participant
        self.room = room

    async def hangup(self):
        try:
            await self.api.room.remove_participant(
                api.RoomParticipantIdentity(
                    room=self.room.name,
                    identity=self.participant.identity,
                )
            )
        except Exception as e:
            # it's possible that the user has already hung up, this error can be ignored
            logger.info(f"received error while ending call: {e}")




eleven_tts=elevenlabs.tts.TTS(
    model="eleven_turbo_v2_5",
    voice=elevenlabs.tts.Voice(
        id="EXAVITQu4vr4xnSDxMaL",
        name="Bella",
        category="premade",
        settings=elevenlabs.tts.VoiceSettings(
            stability=0.71,
            similarity_boost=0.5,
            style=0.0,
            use_speaker_boost=True
        ),
    ),
    language="en",
    streaming_latency=3,
    enable_ssml_parsing=False,
    chunk_length_schedule=[80, 120, 200, 260],
)










def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


if __name__ == "__main__":
    if not outbound_trunk_id or not outbound_trunk_id.startswith("ST_"):
        raise ValueError(
            "SIP_OUTBOUND_TRUNK_ID is not set. Please follow the guide at https://docs.livekit.io/agents/quickstarts/outbound-calls/ to set it up."
        )
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            # giving this agent a name will allow us to dispatch it via API
            # automatic dispatch is disabled when `agent_name` is set
            agent_name="outbound-caller",
            # prewarm by loading the VAD model, needed only for VoicePipelineAgent
            prewarm_fnc=prewarm,
        )
    )
