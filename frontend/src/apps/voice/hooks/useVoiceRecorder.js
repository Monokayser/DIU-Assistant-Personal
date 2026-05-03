import { useEffect, useRef, useState } from "react";
import {
  VOICE_LISTENING_STATUS,
  VOICE_TRANSCRIBING_STATUS,
} from "../../../utils/constants";
import {
  canUseMediaRecorder,
  getBestAudioMimeType,
  getMicrophoneErrorMessage,
  getVoiceMediaStream,
  getVoiceUnsupportedMessage,
} from "../../../utils/common.js";
import { transcribeVoiceInput } from "../../chat/services/assistantService";

export function useVoiceRecorder({ isBusy, onTranscript, setStatus }) {
  const [isListening, setIsListening] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [voiceElapsedSeconds, setVoiceElapsedSeconds] = useState(0);
  const [voiceLevel, setVoiceLevel] = useState(0);
  const [isVoiceRecordingSupported, setIsVoiceRecordingSupported] = useState(true);

  const onTranscriptRef = useRef(onTranscript);
  const mediaRecorderRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const audioChunksRef = useRef([]);
  const voiceAudioContextRef = useRef(null);
  const voiceAnimationRef = useRef(null);
  const voiceLastLevelAtRef = useRef(0);
  const voiceLastLevelRef = useRef(0);
  const voiceStartedAtRef = useRef(0);
  const voiceTimerRef = useRef(null);

  useEffect(() => {
    onTranscriptRef.current = onTranscript;
  }, [onTranscript]);

  useEffect(() => {
    setIsVoiceRecordingSupported(canUseMediaRecorder());
    return () => {
      stopVoiceInput(false);
    };
  }, []);

  function stopVoiceStream() {
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
  }

  function stopVoiceActivityMonitor() {
    if (voiceTimerRef.current) {
      window.clearInterval(voiceTimerRef.current);
      voiceTimerRef.current = null;
    }

    if (voiceAnimationRef.current) {
      cancelAnimationFrame(voiceAnimationRef.current);
      voiceAnimationRef.current = null;
    }

    voiceAudioContextRef.current?.close?.().catch?.(() => {});
    voiceAudioContextRef.current = null;
    voiceLastLevelAtRef.current = 0;
    voiceLastLevelRef.current = 0;
    voiceStartedAtRef.current = 0;
    setVoiceElapsedSeconds(0);
    setVoiceLevel(0);
  }

  function stopVoiceInput(clearStatus = true) {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    } else {
      stopVoiceActivityMonitor();
      stopVoiceStream();
      setIsListening(false);
    }

    if (clearStatus) {
      setStatus((current) => (current === VOICE_LISTENING_STATUS ? "" : current));
    }
  }

  function startVoiceTimer() {
    stopVoiceActivityMonitor();
    voiceStartedAtRef.current = Date.now();
    voiceLastLevelAtRef.current = 0;
    voiceLastLevelRef.current = 0;
    setVoiceElapsedSeconds(0);
    setVoiceLevel(0);

    voiceTimerRef.current = window.setInterval(() => {
      const elapsed = Math.floor((Date.now() - voiceStartedAtRef.current) / 1000);
      setVoiceElapsedSeconds(elapsed);

      if (elapsed >= 60) {
        stopVoiceInput();
        setStatus("Maximum recording length reached (60s).");
      }
    }, 250);
  }

  function startVoiceActivityMonitor(stream, recorder) {
    startVoiceTimer();

    const AudioContextConstructor = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextConstructor) return;

    try {
      const audioContext = new AudioContextConstructor();
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 512;
      audioContext.createMediaStreamSource(stream).connect(analyser);
      voiceAudioContextRef.current = audioContext;

      const samples = new Uint8Array(analyser.fftSize);
      const tick = () => {
        analyser.getByteTimeDomainData(samples);

        let sum = 0;
        for (const sample of samples) {
          const normalized = (sample - 128) / 128;
          sum += normalized * normalized;
        }

        const rms = Math.sqrt(sum / samples.length);
        const nextLevel = Math.min(1, rms * 8);
        const now = Date.now();

        if (
          now - voiceLastLevelAtRef.current > 90
          || Math.abs(nextLevel - voiceLastLevelRef.current) > 0.12
        ) {
          setVoiceLevel(nextLevel);
          voiceLastLevelAtRef.current = now;
          voiceLastLevelRef.current = nextLevel;
        }

        if (recorder.state === "recording") {
          voiceAnimationRef.current = requestAnimationFrame(tick);
        }
      };

      voiceAnimationRef.current = requestAnimationFrame(tick);
    } catch {
      // The timer still gives useful recording feedback if audio analysis is unavailable.
    }
  }

  async function startMediaRecording() {
    setStatus("Requesting microphone...");

    try {
      const stream = await getVoiceMediaStream();
      const mimeType = getBestAudioMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);

      mediaStreamRef.current = stream;
      mediaRecorderRef.current = recorder;
      audioChunksRef.current = [];

      recorder.ondataavailable = (event) => {
        if (event.data?.size) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstart = () => {
        setIsListening(true);
        setStatus(VOICE_LISTENING_STATUS);
        startVoiceActivityMonitor(stream, recorder);
      };

      recorder.onerror = () => {
        stopVoiceActivityMonitor();
        stopVoiceStream();
        setIsListening(false);
        setStatus("Microphone recording stopped unexpectedly.");
      };

      recorder.onstop = async () => {
        const chunks = audioChunksRef.current;
        const recordingType = recorder.mimeType || mimeType || "audio/webm";
        stopVoiceActivityMonitor();
        stopVoiceStream();
        setIsListening(false);

        if (!chunks.length) {
          setStatus("I didn't catch any audio. Tap the mic and try again.");
          return;
        }

        setIsTranscribing(true);
        setStatus(VOICE_TRANSCRIBING_STATUS);

        try {
          const transcript = await transcribeVoiceInput({
            audioBlob: new Blob(chunks, { type: recordingType }),
            language: navigator.language || "en-US",
          });

          if (!transcript) {
            setStatus("");
            return;
          }

          onTranscriptRef.current?.(transcript);
        } catch (error) {
          setStatus(error.message || "Voice transcription failed.");
        } finally {
          audioChunksRef.current = [];
          mediaRecorderRef.current = null;
          setIsTranscribing(false);
        }
      };

      recorder.start(250);
    } catch (error) {
      stopVoiceInput();
      setStatus(await getMicrophoneErrorMessage(error));
    }
  }

  async function handleVoiceInput() {
    if (!isVoiceRecordingSupported) {
      setStatus(getVoiceUnsupportedMessage());
      return;
    }

    if (isBusy || isTranscribing) return;

    if (isListening) {
      stopVoiceInput();
      return;
    }

    if (canUseMediaRecorder()) {
      await startMediaRecording();
      return;
    }

    setStatus(getVoiceUnsupportedMessage());
  }

  return {
    isListening,
    isTranscribing,
    voiceElapsedSeconds,
    voiceLevel,
    handleVoiceInput,
    stopVoiceInput,
  };
}
