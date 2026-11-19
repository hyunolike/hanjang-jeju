using System.Runtime.InteropServices;
using System.Windows;

namespace HanJangJeju;

/// <summary>
/// 사용자 세션마다 프로그램을 하나만 띄운다(P03).
/// 두 번째 실행은 엔진을 켜지 않고 기존 창을 앞으로 부른 뒤 끝난다.
/// 두 창이 같은 작업 폴더를 쓰다가 한쪽의 자동 삭제가 다른 쪽 CSV를 지우는 일을 막는다.
/// </summary>
public partial class App : Application
{
    // 설치 프로그램의 AppMutex와 같은 이름. 접두어가 없으므로 현재 로그인 세션 범위다.
    private const string MutexName = "HanJangJeju.SingleInstance";
    private const string ActivateEventName = "HanJangJeju.Activate";
    private const int ASFW_ANY = -1;

    // GC가 핸들을 닫지 않도록 필드로 쥔다.
    private Mutex? _mutex;
    private bool _ownsMutex;
    private EventWaitHandle? _activate;

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        // 신호 이벤트를 mutex보다 먼저 만들어, 두 번째 실행이 mutex를 보고 이벤트를 찾지 못하는 틈을 없앤다.
        var activate = new EventWaitHandle(false, EventResetMode.AutoReset, ActivateEventName);
        _mutex = new Mutex(true, MutexName, out _ownsMutex);
        if (!_ownsMutex)
        {
            activate.Dispose();
            if (EventWaitHandle.TryOpenExisting(ActivateEventName, out var existing))
            {
                using (existing)
                {
                    // 백그라운드에서 깬 기존 창이 앞으로 나올 수 있게 전경 전환을 허락한다.
                    AllowSetForegroundWindow(ASFW_ANY);
                    existing.Set();
                }
            }
            Shutdown(0);
            return;
        }

        _activate = activate;
        new Thread(WaitForActivation) { IsBackground = true, Name = "single-instance" }.Start();

        MainWindow = new MainWindow();
        MainWindow.Show();
    }

    private void WaitForActivation()
    {
        try
        {
            while (_activate!.WaitOne())
            {
                Dispatcher.BeginInvoke(() =>
                {
                    // 창을 닫는 중(엔진 정리 최대 3초)이면 다시 띄우지 않는다. 그동안의 재실행은 아무 창도 열지 않는다.
                    if (Dispatcher.HasShutdownStarted || MainWindow is not { IsLoaded: true } window) return;
                    window.Show();
                    if (window.WindowState == WindowState.Minimized) window.WindowState = WindowState.Normal;
                    window.Activate();
                    // 전경 잠금으로 Activate가 작업 표시줄 깜빡임에 그칠 때를 대비한다.
                    window.Topmost = true;
                    window.Topmost = false;
                    window.Focus();
                });
            }
        }
        catch (ObjectDisposedException) { }
    }

    protected override void OnExit(ExitEventArgs e)
    {
        if (_mutex != null)
        {
            if (_ownsMutex) _mutex.ReleaseMutex();
            _mutex.Dispose();
        }
        _activate?.Dispose();
        base.OnExit(e);
    }

    [DllImport("user32.dll")]
    private static extern bool AllowSetForegroundWindow(int processId);
}
