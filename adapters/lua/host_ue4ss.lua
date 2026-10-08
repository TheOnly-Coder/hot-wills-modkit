-- hw bridge host-side sketch for UE4SS / REFramework-style Lua (protocol v1).
-- Paste into your mod and fill the GAME-API stubs. TCP JSON-lines to 127.0.0.1:27431.
-- No dependency on `hw` inside the game; validate the session log afterwards with:
--   hw bridge check docs/CONTRACT.md --log bridge.jsonl

local HOST, PORT = "127.0.0.1", 27431
local sock = nil   -- your socket lib here (e.g. LuaSocket); reconnect in a pcall loop

local function now_ms() return math.floor(os.clock() * 1000) end  -- replace with wall clock!

local function send(body)
  body.v, body.stamp = 1, now_ms()
  -- local line = json.encode(body) .. "\n"
  -- sock:send(line)  -- wrap in reconnect logic
end

-- === GAME-API stubs: implement with the host's real scripting API ===
local function get_camera()  -- -> pos {x,y,z} metres, yaw, pitch, fov
  return { pos = { 0, 0, 0 }, yaw = 0, pitch = 0, fov = 70 }
end
local function probe_ground(px, pz, span)  -- -> up to 200 [x,z,y] columns near player
  return {}
end
local function on_guest_event(msg)  -- explosion/projectile/damage/teleport -> act out in host
  -- e.g. if msg.kind == "explosion" then spawn_explosion(msg.at, msg.power) end
end
-- =====================================================================

local function tick()
  local cam = get_camera()
  send({ t = "cam", pos = cam.pos, yaw = cam.yaw, pitch = cam.pitch, fov = cam.fov })
  -- throttle ground to every 3rd frame:
  -- if frame % 3 == 0 then send({ t = "ground", cols = probe_ground(...) }) end
  -- pump inbound lines; dispatch t == "event" to on_guest_event(msg)
end

-- Register tick() as the per-frame callback of your framework (UE4SS: RegisterHook on
-- the player controller tick; REFramework: re.on_frame). Send state heartbeat at 1 Hz.
