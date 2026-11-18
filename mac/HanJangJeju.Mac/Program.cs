using System.Diagnostics;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Reflection;
using Photino.NET;

namespace HanJangJeju.Mac;

/// <summary>
/// Mac용 프로그램 창. 분석 엔진(jeju-engine)을 숨김으로 켜고, 내장 WebKit 창에 화면을 띄운다.
/// 창을 닫으면 엔진을 끈다. 앱이 비정상 종료해도 엔진은 --parent-pid 감시로 스스로 끝난다.
/// </summary>
public static class Program
{
    private static readonly string DataDir = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Library", "Application Support", "HanJangJeju");

    [STAThread]
    public static void Main()
    {
        Directory.CreateDirectory(DataDir);
        var port = FreePort();
        var url = $"http://127.0.0.1:{port}/";
        using var engine = StartEngine(port);

        var window = new PhotinoWindow
        {
            Title = "한 장 제주",
            Width = 1280,
            Height = 860,
            MinWidth = 900,
            MinHeight = 640,
            Centered = true,
            Resizable = true,
            DevToolsEnabled = false,
            ContextMenuEnabled = false,
        };
        window.LoadRawString(Splash().Replace("__ENGINE_URL__", url));
        window.WaitForClose();

        // 엔진을 끄기 전에 "끝낼 때 자동 지우기"를 처리하게 한다. 실패해도 다음에 켤 때 엔진이 지운다.
        try
        {
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(3) };
            http.PostAsync($"{url}api/workspace/exit", null).GetAwaiter().GetResult();
        }
        catch { }
        try { if (!engine.HasExited) engine.Kill(entireProcessTree: true); } catch { }
    }

    private static Process StartEngine(int port)
    {
        // 앱 묶음 안: HanJangJeju.app/Contents/Resources/engine/jeju-engine
        var exe = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "Resources", "engine", "jeju-engine"));
        if (!File.Exists(exe)) exe = Path.Combine(AppContext.BaseDirectory, "engine", "jeju-engine");
        var info = new ProcessStartInfo(exe, $"--port {port} --parent-pid {Environment.ProcessId}")
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            WorkingDirectory = Path.GetDirectoryName(exe)!,
        };
        info.Environment["JEJU_WORKSPACE"] = Path.Combine(DataDir, "workspace");
        info.Environment["NUMBA_CACHE_DIR"] = Path.Combine(DataDir, "numba-cache");
        info.Environment["NIXTLA_NUMBA_CACHE"] = "1";

        var log = new StreamWriter(Path.Combine(DataDir, "engine.log"), append: false) { AutoFlush = true };
        var process = new Process { StartInfo = info };
        process.OutputDataReceived += (_, e) => { if (e.Data != null) lock (log) log.WriteLine(e.Data); };
        process.ErrorDataReceived += (_, e) => { if (e.Data != null) lock (log) log.WriteLine(e.Data); };
        process.Start();
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();
        return process;
    }

    private static string Splash()
    {
        using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("HanJangJeju.Mac.splash.html")!;
        using var reader = new StreamReader(stream);
        return reader.ReadToEnd();
    }

    private static int FreePort()
    {
        var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var port = ((IPEndPoint)listener.LocalEndpoint).Port;
        listener.Stop();
        return port;
    }
}
