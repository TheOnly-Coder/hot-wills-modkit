// hw bridge host-side sketch for BepInEx (protocol v1, Unity/Mono + IL2CPP).
// Drop into your plugin project, fill the GAME-API stubs. Sends cam/ground over
// TCP JSON-lines to 127.0.0.1:27431 on a background thread; applies inbound
// `event` messages on the main thread (Unity API is not thread-safe).
// Validate afterwards: hw bridge check docs/CONTRACT.md --log bridge.jsonl
using System;
using System.Collections.Concurrent;
using System.IO;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using BepInEx;
using UnityEngine;

namespace HotWillsBridge
{
    [BepInPlugin("hw.bridge.host", "HW Bridge Host", "0.1.0")]
    public class BridgeHost : BaseUnityPlugin
    {
        const string Host = "127.0.0.1";
        const int Port = 27431;

        TcpClient client; StreamWriter writer;
        readonly ConcurrentQueue<string> inbox = new ConcurrentQueue<string>();

        void Start()
        {
            new Thread(LinkLoop) { IsBackground = true }.Start();
        }

        static long NowMs() { return DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(); }

        void Send(string body)
        {
            // body already contains t + fields; stamp/version wrapped here
            var line = "{\"v\":1,\"stamp\":" + NowMs() + "," + body + "}\n";
            try { writer.Write(line); writer.Flush(); }
            catch (Exception) { /* LinkLoop reconnects */ }
        }

        void LinkLoop()
        {
            var buf = new byte[65536];
            var pending = new StringBuilder();
            while (true)
            {
                try
                {
                    client = new TcpClient(Host, Port);
                    writer = new StreamWriter(client.GetStream(), Encoding.ASCII);
                    Send("\"t\":\"hello\",\"game\":\"" + GameName() + "\",\"role\":\"host\"");
                    var stream = client.GetStream();
                    while (true)
                    {
                        if (stream.DataAvailable)
                        {
                            int n = stream.Read(buf, 0, buf.Length);
                            if (n <= 0) break;
                            pending.Append(Encoding.ASCII.GetString(buf, 0, n));
                            string s = pending.ToString();
                            int idx;
                            while ((idx = s.IndexOf('\n')) >= 0)
                            {
                                inbox.Enqueue(s.Substring(0, idx));
                                s = s.Substring(idx + 1);
                            }
                            pending = new StringBuilder(s);
                        }
                        else Thread.Sleep(5);
                    }
                }
                catch (Exception) { Thread.Sleep(1000); }  // reconnect forever
            }
        }

        void Update()
        {
            // === GAME-API stubs: replace with the host's real camera/player ===
            var cam = Camera.main;
            if (cam != null)
            {
                var p = cam.transform.position;
                Send(string.Format("\"t\":\"cam\",\"pos\":[{0},{1},{2}],\"yaw\":{3},\"pitch\":{4},\"fov\":{5}",
                    p.x, p.y, p.z, cam.transform.eulerAngles.y, -cam.transform.eulerAngles.x, cam.fieldOfView));
            }
            // ground probes every 3rd frame -> Send("\"t\":\"ground\",\"cols\":[...]");
            // state heartbeat at 1 Hz  -> Send("\"t\":\"state\",\"entities\":0");
            // =================================================================
            while (inbox.TryDequeue(out var line))
            {
                if (line.Contains("\"event\"")) OnGuestEvent(line);  // parse properly in real code
            }
        }

        string GameName() { return Application.productName; }

        void OnGuestEvent(string json)
        {
            // explosion/projectile/damage/teleport -> act out in host on main thread.
        }
    }
}
