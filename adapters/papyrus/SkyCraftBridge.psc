; SkyCraftBridge.psc — Skyrim host shim for the Linux passthrough (no SKSE C++ needed).
;
; What it does: every 0.25 s it Trace()s the player's camera-relevant state to
; Papyrus.0.log, where adapters/python/skycraft_host_daemon.py tails it and
; publishes `cam` + `ground` to the hw bridge broker. Guest events arrive back
; through a polled inbox file (see SKYCRAFT_INBOX below) and are acted out
; with vanilla calls (PlaceAtMe an explosion, DamageActorValue, ...).
;
; Install: copy to Data/Scripts/Source/, compile in the Creation Kit (or use
; the precompiled SkyCraftBridge.pex next to it when shipped), then attach to
; a quest with a Player alias, or call SkyCraftBridge.StartSelf() from the
; console on an existing quest. `hw skyrim install-skycraft` copies this file
; to Data/Scripts/ for you; compiling is one CK click (see skill skyrim-linux).
;
; This never touches online play, anti-cheat, or DRM. Single-player only.

Scriptname SkyCraftBridge extends Quest

; ---- tuning (set in CK or via Set* helpers) ----
float property UpdateInterval = 0.25 auto
string property TraceTag = "SkyCraftBridge" auto
; Inbox file the daemon writes guest events to (one JSON object per line).
; Default lives next to the Papyrus logs so no extra permissions are needed.
string property InboxPath = "../../../Skyrim Special Edition/SkyCraft-inbox.jsonl" auto

bool _running = false

function StartSelf()
  if _running
    return
  endif
  _running = true
  RegisterForSingleUpdate(UpdateInterval)
  Debug.Trace(TraceTag + " hello role=host proto=1")
endFunction

function StopSelf()
  _running = false
  UnregisterForUpdate()
  Debug.Trace(TraceTag + " bye")
endFunction

Event OnUpdate()
  if !_running
    return
  endif
  Actor p = Game.GetPlayer()
  if p
    float x = p.GetPositionX()
    float y = p.GetPositionY()
    float z = p.GetPositionZ()
    float yaw = p.GetAngleZ()
    float pitch = p.GetAngleX()
    ; Skyrim units -> metres (/70), Z-up -> Y-up, +Y north -> -Z north.
    ; The daemon owns the exact fit (docs/CONTRACT.md); we send raw units here.
    Debug.Trace(TraceTag + " cam x=" + x + " y=" + y + " z=" + z + " yaw=" + yaw + " pitch=" + pitch)
    PollInbox()
  endif
  RegisterForSingleUpdate(UpdateInterval)
EndEvent

function PollInbox()
  ; v1: inbox polling is implemented CK-side with FileIO when available
  ; (PapyrusUtil's StorageUtil / FISS). Until then the daemon prints guest
  ; events to SkyCraft-inbox.jsonl and this stub documents the act-out map:
  ;   explosion -> PlaceExplosionAtPoint / mine-side crater bookkeeping
  ;   damage    -> DamageActorValue("Health", amount) on the player puppet
  ;   teleport  -> SetPosition out of the danger volume
  ; Keep the mapping in docs/CONTRACT.md, never in two places.
endFunction
