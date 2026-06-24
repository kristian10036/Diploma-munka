# Live Stabilization Checkpoint

Date: 2026-06-23

This file records the current safe resume point for the live Aaronia RF monitoring stabilization effort.

## Current repository state

- Current commit: `2878a71575a83877964d8b997278c9326271bbc1`
- Working tree: clean
- Local git metadata: `.git-local`
- Remote target provided by user: `https://github.com/kristian10036/Diploma-munka.git`

## What is already preserved

- Baseline documentation exists in `LIVE_STABILIZATION_BASELINE.md`.
- The adaptive viewport controller and its tests are committed.
- Failed Aaronia retune experiments were reverted. The repository is back at the last known stable live state.

## Live state at last verified checkpoint

- Aaronia live stream was restored after the accidental USB disconnect.
- The system was serving real frames again from the live source.
- The risky hard-hardware retune path was not left half-applied.
- No destructive cleanup was performed.

## Current verified runtime

- Backend, frontend, reverse proxy, database, mosquitto, spectrum-ingest, and rf-agent are running.
- `rf-agent` is healthy and the live spectrum WebSocket smoke succeeded.
- The backend health endpoint is reachable through the proxy.
- The current compose runtime is still using the demo profile, so `synthetic_fallback_allowed` is `true` in the live health payload.
- The code path for production live-only fallback gating is committed, but the environment has not been switched to production in this session.

## Most important regression evidence

- Controlled live retune attempts still caused the worker to abort.
- The old wide live frame remained visible, which means the rollback path preserved service continuity.
- Because of that, the Aaronia hardware retune work should stay paused until the source-side sweep/RBW constraints are diagnosed more carefully.

## Safe resume order

1. Keep the current live state as the rollback anchor.
2. Add production live-only synthetic fallback controls without touching the Aaronia data path.
3. Re-open Aaronia retune work only after a narrower diagnostic pass on the worker-side configuration limits.
4. Integrate the frontend viewport controller only after live retune behavior is verified end-to-end.

## Notes for continuation

- Do not treat the untested Aaronia retune path as stable.
- Do not remove mock/replay code.
- Do not perform destructive Docker or data operations.
- If the live stack changes again, refresh this checkpoint before attempting another risky edit.
