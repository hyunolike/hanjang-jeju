using System.IO;
using System.Windows;
using Microsoft.Web.WebView2.Core;

namespace HanJangJeju;

public partial class MainWindow : Window
{
    private EngineHost? _engine;

    public MainWindow()
    {
        InitializeComponent();
        Loaded += async (_, _) => await StartAsync();
        Closed += (_, _) => _engine?.Dispose();
    }

    private async Task StartAsync()
    {
        ShowSplash("분석 엔진을 켜고 있어요", "처음 켤 때는 30초쯤 걸려요. 인터넷 없이 이 PC 안에서만 동작해요.", busy: true);
        try
        {
            _engine?.Dispose();
            _engine = EngineHost.Start();
            await _engine.WaitUntilReadyAsync(TimeSpan.FromSeconds(120));

            var env = await CoreWebView2Environment.CreateAsync(
                userDataFolder: Path.Combine(AppPaths.Data, "webview"));
            await Web.EnsureCoreWebView2Async(env);
            Web.CoreWebView2.Settings.AreDevToolsEnabled = false;
            Web.CoreWebView2.Settings.IsStatusBarEnabled = false;
            // 화면 밖 주소로 나가지 않게 한다. 이 프로그램은 127.0.0.1의 엔진만 연다.
            Web.CoreWebView2.NavigationStarting += (_, e) =>
            {
                if (!e.Uri.StartsWith(_engine!.BaseUrl, StringComparison.OrdinalIgnoreCase)) e.Cancel = true;
            };
            Web.Source = new Uri(_engine.BaseUrl);
            Splash.Visibility = Visibility.Collapsed;
            Web.Visibility = Visibility.Visible;
        }
        catch (WebView2RuntimeNotFoundException)
        {
            ShowSplash("화면 구성 요소가 없어요",
                "Microsoft Edge WebView2 런타임이 필요해요. Windows 11에는 기본으로 들어 있어요. 매뉴얼의 설치 방법을 따라 주세요.", busy: false);
        }
        catch (Exception ex)
        {
            ShowSplash("분석 엔진을 켜지 못했어요", $"{ex.Message}\n기록: {AppPaths.Log}", busy: false);
        }
    }

    private void ShowSplash(string title, string sub, bool busy)
    {
        SplashTitle.Text = title;
        SplashSub.Text = sub;
        SplashProgress.Visibility = busy ? Visibility.Visible : Visibility.Collapsed;
        RetryButton.Visibility = busy ? Visibility.Collapsed : Visibility.Visible;
        Splash.Visibility = Visibility.Visible;
        Web.Visibility = Visibility.Collapsed;
    }

    private async void Retry_Click(object sender, RoutedEventArgs e) => await StartAsync();
}
