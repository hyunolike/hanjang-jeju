using System.Diagnostics;
using System.IO;
using System.Windows;
using System.Windows.Threading;
using Microsoft.Web.WebView2.Core;

namespace HanJangJeju;

public partial class MainWindow : Window
{
    private const string FirstRunNote = "처음 켤 때는 30초쯤 걸려요. 인터넷 없이 이 PC 안에서만 동작해요.";
    private const string SlowNote = "생각보다 오래 걸리고 있어요. 처음 켤 때는 1분 넘게 걸리기도 해요.";
    private const string AskStaff = "그래도 안 되면 기록 폴더의 파일을 센터 담당자에게 보여 주세요.";

    private EngineHost? _engine;
    private bool _busy;

    // 30초가 지나도 끝나지 않으면 보조 문장을 바꿔, 멈춘 것이 아니라는 것을 알린다.
    // 가짜 퍼센트 진행률은 쓰지 않는다. 엔진이 진행 정도를 알려 주지 않기 때문이다.
    private readonly DispatcherTimer _slowTimer = new() { Interval = TimeSpan.FromSeconds(30) };

    public MainWindow()
    {
        InitializeComponent();
        // WebView2의 기본 바탕을 흰색이 아닌 앱 바탕색으로 맞춰, 첫 그림이 그려지기 전의 번쩍임을 없앤다.
        Web.DefaultBackgroundColor = System.Drawing.Color.FromArgb(0xF2, 0xF4, 0xF6);
        _slowTimer.Tick += (_, _) =>
        {
            _slowTimer.Stop();
            if (_busy) SplashSub.Text = SlowNote;
        };
        Loaded += async (_, _) => await StartAsync();
        Closed += (_, _) => _engine?.Dispose();
    }

    private async Task StartAsync()
    {
        ShowBusy("분석 엔진을 켜고 있어요", FirstRunNote);
        _slowTimer.Stop();
        _slowTimer.Start();
        try
        {
            _engine?.Dispose();
            _engine = EngineHost.Start();
            await _engine.WaitUntilReadyAsync(TimeSpan.FromSeconds(120));

            ShowBusy("화면을 준비하고 있어요", "거의 다 됐어요.");
            if (Web.CoreWebView2 == null)
            {
                var env = await CoreWebView2Environment.CreateAsync(
                    userDataFolder: Path.Combine(AppPaths.Data, "webview"));
                await Web.EnsureCoreWebView2Async(env);
                var core = Web.CoreWebView2!;
                core.Settings.AreDevToolsEnabled = false;
                core.Settings.IsStatusBarEnabled = false;
                // 화면 밖 주소로 나가지 않게 한다. 이 프로그램은 127.0.0.1의 엔진만 연다.
                core.NavigationStarting += (_, e) =>
                {
                    if (_engine == null || !e.Uri.StartsWith(_engine.BaseUrl, StringComparison.OrdinalIgnoreCase))
                        e.Cancel = true;
                };
            }

            // 첫 페이지가 다 그려진 뒤에 시작 화면을 걷는다.
            if (!await NavigateAsync(_engine.BaseUrl, TimeSpan.FromSeconds(30)))
                throw new InvalidOperationException("첫 화면을 불러오지 못했어요.");

            _busy = false;
            _slowTimer.Stop();
            Web.Visibility = Visibility.Visible;
            Splash.Visibility = Visibility.Collapsed;
        }
        catch (WebView2RuntimeNotFoundException ex)
        {
            Record(ex);
            ShowProblem("화면을 띄울 구성 요소가 없어요",
                "Microsoft Edge WebView2 런타임이 필요해요. 매뉴얼의 설치 순서대로 설치한 뒤 다시 시도해 주세요.",
                showLog: false);
        }
        catch (FileNotFoundException ex)
        {
            Record(ex);
            ShowProblem("분석 엔진 파일이 없어요",
                "설치가 끝까지 되지 않은 것 같아요. 한 장 제주를 다시 설치해 주세요.", showLog: false);
        }
        catch (TimeoutException ex)
        {
            Record(ex);
            ShowProblem("켜는 데 너무 오래 걸리고 있어요",
                $"PC를 다시 켠 뒤 한 번 더 열어 주세요. {AskStaff}", showLog: true);
        }
        catch (Exception ex)
        {
            Record(ex);
            ShowProblem("분석 엔진을 켜지 못했어요", $"다시 시도해 주세요. {AskStaff}", showLog: true);
        }
    }

    private async Task<bool> NavigateAsync(string url, TimeSpan timeout)
    {
        var done = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        void OnCompleted(object? sender, CoreWebView2NavigationCompletedEventArgs e)
        {
            Web.CoreWebView2.NavigationCompleted -= OnCompleted;
            done.TrySetResult(e.IsSuccess);
        }
        Web.CoreWebView2.NavigationCompleted += OnCompleted;
        Web.CoreWebView2.Navigate(url);
        try
        {
            return await done.Task.WaitAsync(timeout);
        }
        finally
        {
            Web.CoreWebView2.NavigationCompleted -= OnCompleted;
        }
    }

    private void ShowBusy(string title, string sub)
    {
        _busy = true;
        SplashTitle.Text = title;
        SplashSub.Text = sub;
        SplashProgress.Visibility = Visibility.Visible;
        RetryButton.Visibility = Visibility.Collapsed;
        LogButton.Visibility = Visibility.Collapsed;
        Splash.Visibility = Visibility.Visible;
        Web.Visibility = Visibility.Collapsed;
    }

    // 무엇이 안 됐는지(제목)와 무엇을 하면 되는지(보조 문장)만 보인다. 예외 원문과 경로는 기록 파일에 남긴다.
    private void ShowProblem(string title, string sub, bool showLog)
    {
        _busy = false;
        _slowTimer.Stop();
        SplashTitle.Text = title;
        SplashSub.Text = sub;
        SplashProgress.Visibility = Visibility.Collapsed;
        RetryButton.Visibility = Visibility.Visible;
        LogButton.Visibility = showLog ? Visibility.Visible : Visibility.Collapsed;
        Splash.Visibility = Visibility.Visible;
        Web.Visibility = Visibility.Collapsed;
    }

    private static string LauncherLog => Path.Combine(AppPaths.Data, "launcher.log");

    private static void Record(Exception ex)
    {
        try
        {
            Directory.CreateDirectory(AppPaths.Data);
            File.AppendAllText(LauncherLog, $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {ex}{Environment.NewLine}");
        }
        catch { }
    }

    private async void Retry_Click(object sender, RoutedEventArgs e) => await StartAsync();

    private void Log_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            Directory.CreateDirectory(AppPaths.Data);
            Process.Start(new ProcessStartInfo("explorer.exe", $"\"{AppPaths.Data}\"") { UseShellExecute = true });
        }
        catch (Exception ex) { Record(ex); }
    }
}
