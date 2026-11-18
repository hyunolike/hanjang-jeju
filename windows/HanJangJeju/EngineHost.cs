using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Runtime.InteropServices;

namespace HanJangJeju;

/// <summary>사용자 영역의 프로그램 자료 위치.</summary>
public static class AppPaths
{
    public static string Data { get; } = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "HanJangJeju");

    public static string Workspace => Path.Combine(Data, "workspace");
    public static string Log => Path.Combine(Data, "engine.log");
    public static string Engine => Path.Combine(AppContext.BaseDirectory, "engine", "jeju-engine.exe");
}

/// <summary>
/// 분석 엔진(jeju-engine.exe)을 숨김 창으로 켜고 끈다.
/// Windows Job Object에 묶어 이 프로그램이 어떻게 끝나든 엔진이 남지 않게 한다.
/// </summary>
public sealed class EngineHost : IDisposable
{
    private readonly Process _process;
    private readonly IntPtr _job;
    public int Port { get; }
    public string BaseUrl => $"http://127.0.0.1:{Port}/";

    private EngineHost(Process process, IntPtr job, int port)
    {
        _process = process;
        _job = job;
        Port = port;
    }

    public static EngineHost Start()
    {
        if (!File.Exists(AppPaths.Engine))
            throw new FileNotFoundException("분석 엔진 파일이 없어요. 프로그램을 다시 설치해 주세요.", AppPaths.Engine);
        Directory.CreateDirectory(AppPaths.Data);
        var port = FreePort();
        var info = new ProcessStartInfo(AppPaths.Engine, $"--port {port}")
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            WorkingDirectory = Path.GetDirectoryName(AppPaths.Engine)!,
        };
        info.Environment["JEJU_WORKSPACE"] = AppPaths.Workspace;
        info.Environment["NUMBA_CACHE_DIR"] = Path.Combine(AppPaths.Data, "numba-cache");
        info.Environment["NIXTLA_NUMBA_CACHE"] = "1";
        info.Environment["PYTHONUTF8"] = "1";

        var log = new StreamWriter(AppPaths.Log, append: false) { AutoFlush = true };
        var process = new Process { StartInfo = info, EnableRaisingEvents = true };
        process.OutputDataReceived += (_, e) => { if (e.Data != null) lock (log) log.WriteLine(e.Data); };
        process.ErrorDataReceived += (_, e) => { if (e.Data != null) lock (log) log.WriteLine(e.Data); };
        process.Start();
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();
        var job = Job.CreateKillOnClose();
        Job.Assign(job, process);
        return new EngineHost(process, job, port);
    }

    public async Task WaitUntilReadyAsync(TimeSpan timeout)
    {
        using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };
        var until = DateTime.UtcNow + timeout;
        while (DateTime.UtcNow < until)
        {
            if (_process.HasExited)
                throw new InvalidOperationException($"분석 엔진이 멈췄어요 (종료 코드 {_process.ExitCode}).");
            try
            {
                var res = await http.GetAsync($"{BaseUrl}api/health");
                if (res.IsSuccessStatusCode) return;
            }
            catch (HttpRequestException) { }
            catch (TaskCanceledException) { }
            await Task.Delay(500);
        }
        throw new TimeoutException("분석 엔진이 2분 안에 준비되지 않았어요.");
    }

    private static int FreePort()
    {
        var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var port = ((IPEndPoint)listener.LocalEndpoint).Port;
        listener.Stop();
        return port;
    }

    public void Dispose()
    {
        // 엔진을 끄기 전에 "끝낼 때 자동 지우기"를 처리하게 한다. 실패해도 다음에 켤 때 엔진이 지운다.
        try
        {
            if (!_process.HasExited)
            {
                using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(3) };
                http.PostAsync($"{BaseUrl}api/workspace/exit", null).GetAwaiter().GetResult();
            }
        }
        catch { }
        try { if (!_process.HasExited) _process.Kill(entireProcessTree: true); } catch { }
        Job.Close(_job);
        _process.Dispose();
    }

    /// <summary>프로그램이 끝나면 묶인 프로세스를 모두 끄는 Windows Job Object.</summary>
    private static class Job
    {
        private const int JobObjectExtendedLimitInformation = 9;
        private const uint JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000;

        public static IntPtr CreateKillOnClose()
        {
            var handle = CreateJobObject(IntPtr.Zero, null);
            var info = new JOBOBJECT_EXTENDED_LIMIT_INFORMATION();
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            var size = Marshal.SizeOf(info);
            var ptr = Marshal.AllocHGlobal(size);
            try
            {
                Marshal.StructureToPtr(info, ptr, false);
                SetInformationJobObject(handle, JobObjectExtendedLimitInformation, ptr, (uint)size);
            }
            finally { Marshal.FreeHGlobal(ptr); }
            return handle;
        }

        public static void Assign(IntPtr job, Process process) => AssignProcessToJobObject(job, process.Handle);

        public static void Close(IntPtr job)
        {
            if (job != IntPtr.Zero) CloseHandle(job);
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct JOBOBJECT_BASIC_LIMIT_INFORMATION
        {
            public long PerProcessUserTimeLimit;
            public long PerJobUserTimeLimit;
            public uint LimitFlags;
            public UIntPtr MinimumWorkingSetSize;
            public UIntPtr MaximumWorkingSetSize;
            public uint ActiveProcessLimit;
            public UIntPtr Affinity;
            public uint PriorityClass;
            public uint SchedulingClass;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct IO_COUNTERS
        {
            public ulong ReadOperationCount, WriteOperationCount, OtherOperationCount;
            public ulong ReadTransferCount, WriteTransferCount, OtherTransferCount;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION
        {
            public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;
            public IO_COUNTERS IoInfo;
            public UIntPtr ProcessMemoryLimit;
            public UIntPtr JobMemoryLimit;
            public UIntPtr PeakProcessMemoryUsed;
            public UIntPtr PeakJobMemoryUsed;
        }

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
        private static extern IntPtr CreateJobObject(IntPtr attributes, string? name);

        [DllImport("kernel32.dll")]
        private static extern bool SetInformationJobObject(IntPtr job, int infoClass, IntPtr info, uint length);

        [DllImport("kernel32.dll")]
        private static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);

        [DllImport("kernel32.dll")]
        private static extern bool CloseHandle(IntPtr handle);
    }
}
