"""Exercise the shipping click loop with deterministic Windows API substitutes.

No native imports survive compilation; tests never move the Windows cursor.
Run with the system Python on Windows. The installed connector is untouched.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile


HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent / 'payload' / 'desktop.ps1'
CODES = {
    'IsWindow': 'return h != IntPtr.Zero;',
    'IsWindowVisible': 'return h != IntPtr.Zero;',
    'IsWindowEnabled': 'return h != IntPtr.Zero;',
    'GetWindowThreadProcessId': 'pid=7; return 1;',
    'GetClassName': 'b.Append(FakeClass(h)); return b.Length;',
    'GetWindowText': 'return 0;',
    'GetShellWindow': 'return Desktop;',
    'FindWindowEx': 'return parent==Desktop && cls=="SHELLDLL_DefView" ? View : parent==View && cls=="SysListView32" ? List : IntPtr.Zero;',
    'GetStyle': 'return 0;',
    'GetForegroundWindow': 'return FakeForeground();',
    'SetForegroundWindow': 'return false;',
    'GetAncestor': 'return h==List ? (flags==1 ? View : Desktop) : h==View ? Desktop : h;',
    'CreateGuardWindow': 'return new IntPtr(6);',
    'DestroyWindow': 'return true;',
    'RegisterRawInputDevices': 'return true;',
    'PeekMessage': 'msg=new WindowMessage(); return false;',
    'GetClientRect': 'rect=new Rect{right=200,bottom=200}; return true;',
    'ClientToScreen': 'return true;',
    'ScreenToClient': 'return true;',
    'SetCursorPos': 'Cursor.x=x; Cursor.y=y; return true;',
    'GetCursorPos': 'pt=Cursor; return true;',
    'WindowFromPoint': 'return Receiver;',
    'AccessibleObjectFromPoint': 'bool self=Case=="item_self"; element=self ? (IAccessible)FakeIcon : FakeList; child=self || Case=="blank" ? 0 : 1; return 0;',
    'WindowFromAccessibleObject': 'window=List; return 0;',
    'AccessibleObjectFromWindow': 'element=FakeList; return 0;',
    'AccessibleChildren': 'actual=start==0 ? 1 : 0; if(actual==1)children[0]=1; return 0;',
    'GetAnimationSetting': 'enabled=0; return true;',
    'IsIconic': 'return false;',
    'IsZoomed': 'return false;',
    'GetDoubleClickTime': 'return 500;',
    'GetGUIThreadInfo': 'return true;',
    'GetLastInputInfo': 'info.tick=1; return true;',
    'GetDpiForWindow': 'return 96;',
    'GetAsyncKeyState': 'return 0;',
    'SendInput': 'return FakeSend(n, inputs);',
}


def instrument(source):
    source = re.search(r"@'\s*\n(using System;.*?public static class WBWin\s*\{.*?)\r?\n'@", source, re.S).group(1)
    native = re.compile(r'\[DllImport\([^\n]*?\)\]\s*((?:public\s+)?static extern [\s\S]*?);')

    def replace(match):
        declaration = match[1].replace('static extern', 'static', 1)
        name = re.search(r'\b(\w+)\s*\(', declaration)[1]
        body = CODES.get(name, f'throw new NotSupportedException("unstubbed {name}");')
        return declaration + '{' + body + '}'

    source = native.sub(replace, source).replace('public static class WBWin', 'public static partial class WBWin', 1)
    if re.search(r'DllImport|\bextern\b', source):
        raise RuntimeError('A native import survived substitution; refusing to run')
    return source


def main():
    compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    with tempfile.TemporaryDirectory(prefix='wb-click-test-') as temp:
        temp = Path(temp)
        instrumented = temp / 'WBWin.cs'
        instrumented.write_text(instrument(BACKEND.read_text(encoding='utf-8-sig')), encoding='utf-8-sig')
        exe = temp / 'guard-tests.exe'
        subprocess.run([str(compiler), '/nologo', '/r:Accessibility.dll', '/r:System.Windows.Forms.dll',
                        '/r:System.Drawing.dll', f'/out:{exe}', str(instrumented),
                        str(HERE / 'test_shell143_driver.cs')], cwd=temp, check=True)
        for case in ('visible', 'item_self', 'activate_between', 'occluded', 'blank', 'unknown_foreground',
                     'changed_receiver', 'move_between', 'focus_between', 'regain_prior', 'item_between', 'ordinary'):
            subprocess.run([str(exe), case, str(temp / (case + '.json'))], cwd=temp, check=True)


if __name__ == '__main__':
    main()
