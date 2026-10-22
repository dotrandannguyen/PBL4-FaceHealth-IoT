using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Windows.Forms;

// Build into <project>/.pbl4-run/FaceCheckin.exe; no terminal or shell commands.
internal static class FaceCheckinLauncher
{
    [STAThread]
    private static void Main()
    {
        string run = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
        string root = Directory.GetParent(run).FullName;
        string ai = Path.Combine(root, "pbl4-face-ai");
        try
        {
            ProcessStartInfo start = new ProcessStartInfo();
            start.FileName = Path.Combine(ai, @".venv-pbl4\Scripts\python.exe");
#if STATUS_TEST
            start.Arguments = "-u -B \"" + Path.Combine(ai, "gui_status.py") + "\"";
            string logPrefix = "desktop-status-test";
#elif REGISTRATION
            start.Arguments = "-u -B \"" + Path.Combine(ai, "gui_register.py") + "\"";
            string logPrefix = "desktop-registration";
#elif DASHBOARD
            start.Arguments = "-u -B \"" + Path.Combine(ai, "gui.py") + "\"";
            string logPrefix = "desktop-dashboard";
#elif ATTENDANCE_AI2
            start.Arguments = "-u -B \"" + Path.Combine(ai, "gui_attendance.py") + "\"";
            string logPrefix = "desktop-attendance-ai2";
#else
            start.Arguments = "-u -B \"" + Path.Combine(ai, "gui_attendance.py") + "\"";
            string logPrefix = "desktop-checkin";
#endif
            start.WorkingDirectory = ai;
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            start.RedirectStandardOutput = true;
            start.RedirectStandardError = true;
            start.StandardOutputEncoding = Encoding.UTF8;
            start.StandardErrorEncoding = Encoding.UTF8;
            start.EnvironmentVariables["PYTHONUTF8"] = "1";
            start.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
            using (StreamWriter output = new StreamWriter(Path.Combine(run, logPrefix + ".out.log"), false, Encoding.UTF8))
            using (StreamWriter error = new StreamWriter(Path.Combine(run, logPrefix + ".err.log"), false, Encoding.UTF8))
            using (Process child = new Process())
            {
                output.AutoFlush = error.AutoFlush = true;
                child.StartInfo = start;
                child.OutputDataReceived += delegate(object sender, DataReceivedEventArgs e) { if (e.Data != null) output.WriteLine(e.Data); };
                child.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs e) { if (e.Data != null) error.WriteLine(e.Data); };
                child.Start();
                child.BeginOutputReadLine();
                child.BeginErrorReadLine();
                child.WaitForExit();
                if (child.ExitCode != 0)
                    MessageBox.Show("Ung dung da dung. Xem .pbl4-run/" + logPrefix + ".err.log", "PBL4");
            }
        }
        catch (Exception)
        {
            MessageBox.Show("Khong mo duoc ung dung. Kiem tra duong dan du an va moi truong Python.", "PBL4");
        }
    }
}
