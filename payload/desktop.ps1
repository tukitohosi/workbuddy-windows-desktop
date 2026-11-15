$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8

function Assert-DesktopActive {
    if ($script:request.cancel_path -and [IO.File]::Exists($script:request.cancel_path)) { throw 'Desktop operation cancelled.' }
}
function Start-DesktopEffect {
    Assert-DesktopActive
    if ($script:request.started_path) {[IO.File]::WriteAllText($script:request.started_path,'1')}
    Assert-DesktopActive
}
function Set-DesktopReceipt($receipt) {
    if (!$script:request.receipt_path) {return}
    $dest=$script:request.receipt_path
    $temp=$dest+'.ps.tmp'
    [IO.File]::WriteAllText($temp,($receipt | ConvertTo-Json -Compress -Depth 5),$utf8)
    if ([IO.File]::Exists($dest)) {[IO.File]::Replace($temp,$dest,[System.Management.Automation.Language.NullString]::Value)}
    else {[IO.File]::Move($temp,$dest)}
}

function Initialize-Desktop {
    Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
    Add-Type -ReferencedAssemblies 'System.dll','Accessibility.dll' -TypeDefinition @'
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using Accessibility;
public static class WBWin {
    public delegate bool EnumProc(IntPtr h, IntPtr p);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc cb,IntPtr p);
    [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr h,EnumProc cb,IntPtr p);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern bool IsWindowEnabled(IntPtr h);
    [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr h);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h,out uint pid);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr h,StringBuilder b,int n);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h,StringBuilder b,int n);
    [DllImport("user32.dll")] static extern IntPtr GetShellWindow();
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern IntPtr FindWindowEx(IntPtr parent,IntPtr previous,string cls,string title);
    [DllImport("user32.dll",EntryPoint="GetWindowLongW")] public static extern int GetStyle(IntPtr h,int idx);
    [DllImport("user32.dll",CharSet=CharSet.Unicode,EntryPoint="SendMessageTimeoutW")]
    static extern IntPtr Msg(IntPtr h,uint m,IntPtr w,IntPtr l,uint flags,uint ms,out IntPtr result);
    [StructLayout(LayoutKind.Sequential)]
    struct Point {public int x, y;}
    [StructLayout(LayoutKind.Sequential)]
    struct Rect {public int left,top,right,bottom;}
    [StructLayout(LayoutKind.Sequential)]
    struct MouseInput {public int dx,dy; public uint data,flags,time; public UIntPtr extra;}
    [StructLayout(LayoutKind.Sequential)]
    struct Input {public uint type; public MouseInput mouse;}
    [StructLayout(LayoutKind.Sequential)]
    struct GuiThreadInfo {public int size, flags; public IntPtr active, focus, capture, menuOwner, moveSize, caret; public Rect caretRect;}
    [StructLayout(LayoutKind.Sequential)]
    struct LastInputInfo {public uint size, tick;}
    [StructLayout(LayoutKind.Sequential)]
    struct RawDevice {public ushort page,usage; public uint flags; public IntPtr target;}
    [StructLayout(LayoutKind.Sequential)]
    struct RawHeader {public uint type,size; public IntPtr device,param;}
    [StructLayout(LayoutKind.Sequential)]
    struct WindowMessage {public IntPtr hwnd; public uint id; public UIntPtr wp; public IntPtr lp; public uint time; public Point pos; public uint priv;}
    [DllImport("user32.dll",CharSet=CharSet.Unicode,EntryPoint="CreateWindowExW")]
    static extern IntPtr CreateGuardWindow(uint extra,string cls,string name,uint style,int x,int y,int width,int height,IntPtr parent,IntPtr menu,IntPtr app,IntPtr args);
    [DllImport("user32.dll")] static extern bool DestroyWindow(IntPtr h);
    [DllImport("user32.dll")] static extern bool RegisterRawInputDevices(RawDevice[] devices,uint count,uint size);
    [DllImport("user32.dll",EntryPoint="PeekMessageW")] static extern bool PeekMessage(out WindowMessage msg,IntPtr hwnd,uint min,uint max,uint flags);
    [DllImport("user32.dll",EntryPoint="DefWindowProcW")] static extern IntPtr DefaultMessage(IntPtr h,uint msg,UIntPtr wp,IntPtr lp);
    [DllImport("user32.dll",EntryPoint="GetRawInputData")] static extern uint RawHeaderOnly(IntPtr input,uint command,out RawHeader header,ref uint size,uint headerSize);
    [DllImport("user32.dll",EntryPoint="GetRawInputData")] static extern uint RawMouseData(IntPtr input,uint command,IntPtr buffer,ref uint size,uint headerSize);
    [DllImport("user32.dll")] static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
    [DllImport("user32.dll")] static extern bool GetClientRect(IntPtr h,out Rect rect);
    [DllImport("user32.dll")] static extern bool ClientToScreen(IntPtr h,ref Point pt);
    [DllImport("user32.dll")] static extern bool SetCursorPos(int x,int y);
    [DllImport("user32.dll")] static extern bool GetCursorPos(out Point pt);
    [DllImport("user32.dll", EntryPoint="SystemParametersInfoW")]
    static extern bool GetAnimationSetting(uint action,uint unused,out int enabled,uint flags);
    [DllImport("user32.dll")] static extern IntPtr WindowFromPoint(Point pt);
    [DllImport("oleacc.dll")] static extern int AccessibleObjectFromPoint(Point pt,[MarshalAs(UnmanagedType.Interface)] out IAccessible element,[MarshalAs(UnmanagedType.Struct)] out object child);
    [DllImport("oleacc.dll")] static extern int WindowFromAccessibleObject(IAccessible element,out IntPtr window);
    [DllImport("oleacc.dll")] static extern int AccessibleObjectFromWindow(IntPtr hwnd,uint objectId,ref Guid iid,[MarshalAs(UnmanagedType.Interface)] out IAccessible element);
    [DllImport("oleacc.dll")] static extern int AccessibleChildren(IAccessible parent,int start,int count,[Out,MarshalAs(UnmanagedType.LPArray,ArraySubType=UnmanagedType.Struct,SizeParamIndex=2)] object[] children,out int actual);
    [DllImport("user32.dll")] static extern IntPtr GetAncestor(IntPtr h,uint flags);
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] static extern bool IsZoomed(IntPtr h);
    [DllImport("user32.dll")] static extern uint GetDoubleClickTime();
    [DllImport("user32.dll")] static extern bool ScreenToClient(IntPtr h,ref Point pt);
    [DllImport("user32.dll")] static extern bool ShowWindowAsync(IntPtr h,int cmd);
    [DllImport("user32.dll")] static extern bool GetGUIThreadInfo(uint threadId,ref GuiThreadInfo info);
    [DllImport("user32.dll")] static extern bool GetLastInputInfo(ref LastInputInfo info);
    [DllImport("user32.dll")] static extern uint GetDpiForWindow(IntPtr h);
    [DllImport("user32.dll")] static extern short GetAsyncKeyState(int key);
    [DllImport("user32.dll",SetLastError=true)] static extern uint SendInput(uint n,Input[] inputs,int size);
    public static void PhysicalCoordinates(){
        if (SetThreadDpiAwarenessContext(new IntPtr(-4))==IntPtr.Zero &&
            SetThreadDpiAwarenessContext(new IntPtr(-3))==IntPtr.Zero)
            throw new Exception("Per-monitor DPI mode is required for desktop coordinates.");
    }
    static int[] TryClientBounds(IntPtr h){
        Rect r; var origin=new Point();
        if(!GetClientRect(h,out r)||!ClientToScreen(h,ref origin)||r.right<=r.left||r.bottom<=r.top)
            return null;
        return new[]{origin.x,origin.y,r.right-r.left,r.bottom-r.top};
    }
    public static int[] ClientBounds(IntPtr h){
        var bounds=TryClientBounds(h);
        if(bounds==null)throw new Exception("Window has no usable client area.");
        return bounds;
    }
    public static bool TargetFront(IntPtr h){return GetAncestor(GetForegroundWindow(),2)==h;}
    public static string State(IntPtr h){
        if(!IsWindow(h))throw new Exception("Selected window was closed.");
        return IsIconic(h)?"minimized":IsZoomed(h)?"maximized":"normal";
    }
    public static string ChangeState(IntPtr h,string action){
        string before=State(h);
        if(action=="query")return before;
        int command;
        if(action=="restore")command=9;
        else if(action=="maximize")command=3;
        else if(action=="minimize")command=6;
        else throw new Exception("Window action must be query, restore, maximize or minimize.");
        // SW_RESTORE on a minimized, previously maximized window may return it to maximized.
        // An already maximized window can also explicitly be restored to normal.
        if((action=="restore"&&before=="normal")||(action=="maximize"&&before=="maximized")||
           (action=="minimize"&&before=="minimized"))return before;
        if(!ShowWindowAsync(h,command))throw new Exception("Window state command could not be queued.");
        for(int i=0;i<60;i++){
            string now=State(h);
            if((action=="restore"&&(before=="minimized"?now!="minimized":now=="normal"))||
               (action=="maximize"&&now=="maximized")||(action=="minimize"&&now=="minimized"))return now;
            System.Threading.Thread.Sleep(20);
        }
        throw new Exception("Window did not reach the requested state; actual state: "+State(h));
    }
    static IntPtr initialFront;
    static uint initialInput;
    static Point initialCursor;
    static int[] initialBounds;
    static uint initialDpi;
    static int pointerPid;
    static string pointerMarker;
    static int[] readyBounds;
    static uint readyDpi;
    static IntPtr guardWindow,mouseBuffer;
    static readonly uint rawHeaderSize=(uint)Marshal.SizeOf(typeof(RawHeader));
    static readonly uint rawDeviceSize=(uint)Marshal.SizeOf(typeof(RawDevice));
    static readonly System.Diagnostics.Stopwatch quiet=new System.Diagnostics.Stopwatch();
    static bool hadTargetForeground;
    sealed class DesktopIcon {
        public IntPtr list;
        public string name;
        public int childId,ordinal=-1;
        public int[] bounds;
    }
    static DesktopIcon desktopIcon;
    public static bool DesktopIconVerified {get{return desktopIcon!=null;}}
    public static int InputClockChanges,PointerChanges;
    public static string GuardReason="none";
    public static string ActivationMethod;
    public static bool ActivationCycleSubmitted;
    static Exception GuardFailure(string reason,string message){
        GuardReason=reason;return new Exception(message);
    }
    static RawDevice[] GuardDevices(uint flags,IntPtr target){
        return new[]{new RawDevice{page=1,usage=2,flags=flags,target=target},
                     new RawDevice{page=1,usage=6,flags=flags,target=target}};
    }
    static void StartInputGuard(){
        guardWindow=CreateGuardWindow(0,"STATIC",null,0,0,0,0,0,new IntPtr(-3),IntPtr.Zero,IntPtr.Zero,IntPtr.Zero);
        if(guardWindow==IntPtr.Zero||!RegisterRawInputDevices(GuardDevices(0x100,guardWindow),2,rawDeviceSize))
            throw GuardFailure("input_observer_unavailable","Cannot verify physical input during window activation.");
        mouseBuffer=Marshal.AllocHGlobal(64);
        quiet.Restart();
    }
    public static void EndInputGuard(){
        if(guardWindow!=IntPtr.Zero){
            RegisterRawInputDevices(GuardDevices(1,IntPtr.Zero),2,rawDeviceSize);
            DestroyWindow(guardWindow);guardWindow=IntPtr.Zero;
        }
        if(mouseBuffer!=IntPtr.Zero){Marshal.FreeHGlobal(mouseBuffer);mouseBuffer=IntPtr.Zero;}
    }
    static void CheckPhysicalInput(){
        if(guardWindow==IntPtr.Zero)return;
        WindowMessage msg;
        // No key codes, key state arrays, or text are requested. A keyboard
        // packet's device type alone is sufficient to yield control.
        while(PeekMessage(out msg,guardWindow,0xFF,0xFF,1)){
            try {
                CheckCancellation();
                RawHeader head;
                uint size=rawHeaderSize;
                if(RawHeaderOnly(msg.lp,0x10000005,out head,ref size,rawHeaderSize)!=rawHeaderSize)
                    throw GuardFailure("input_observer_unavailable","Cannot classify an input event.");
                if(head.type==1)throw GuardFailure("keyboard_activity","Keyboard activity interrupted window activation.");
                if(head.type==0){
                    size=64;
                    uint count=RawMouseData(msg.lp,0x10000003,mouseBuffer,ref size,rawHeaderSize);
                    if(count==UInt32.MaxValue||count<rawHeaderSize+6)
                        throw GuardFailure("input_observer_unavailable","Cannot classify a pointer event.");
                    if(Marshal.ReadInt16(mouseBuffer,(int)rawHeaderSize+4)!=0)
                        throw GuardFailure("pointer_button_activity","Mouse button or wheel activity interrupted the action.");
                }
            } finally {DefaultMessage(msg.hwnd,msg.id,msg.wp,msg.lp);}
        }
        var gui=new GuiThreadInfo{size=Marshal.SizeOf(typeof(GuiThreadInfo))};
        if(!GetGUIThreadInfo(0,ref gui)||gui.capture!=IntPtr.Zero||gui.moveSize!=IntPtr.Zero||gui.menuOwner!=IntPtr.Zero)
            throw GuardFailure("capture_or_menu","A drag, capture or open menu prevents pointer control.");
        foreach(int key in new[]{1,2,4,5,6,16,17,18,91,92})
            if((GetAsyncKeyState(key)&0x8000)!=0)throw GuardFailure("button_or_modifier_held","Release the mouse buttons and modifiers before pointer control.");
    }
    static uint LastInput(){
        var info=new LastInputInfo{size=(uint)Marshal.SizeOf(typeof(LastInputInfo))};
        if(!GetLastInputInfo(ref info))throw new Exception("Cannot verify the interactive input state.");
        return info.tick;
    }
    static void CheckActivation(IntPtr h){
        CheckCancellation();
        CheckPhysicalInput();
        if(!IsWindow(h)||!IsWindowEnabled(h)||!IsWindowVisible(h)||Pid(h)!=pointerPid||
           (!String.IsNullOrEmpty(pointerMarker)&&!Title(h).Contains(pointerMarker)))
            throw new Exception("Selected window was closed, hidden or blocked by a dialog.");
        Point cursor;
        if(!GetCursorPos(out cursor))throw GuardFailure("position_unavailable","Cannot verify the pointer position.");
        if(cursor.x!=initialCursor.x||cursor.y!=initialCursor.y){
            PointerChanges++;initialCursor=cursor;quiet.Restart();
        }
        uint tick=LastInput();
        if(tick!=initialInput){InputClockChanges++;initialInput=tick;}
        CheckPointerForeground(h,false);
    }
    static void CheckPointerForeground(IntPtr h,bool requireKnown){
        IntPtr current=GetAncestor(GetForegroundWindow(),2);
        if(current==h)hadTargetForeground=true;
        else if(current==IntPtr.Zero&&requireKnown)
            throw GuardFailure("foreground_unavailable","Cannot confirm the foreground window before pointer input.");
        else if(current!=IntPtr.Zero&&(current!=initialFront||hadTargetForeground))
            throw GuardFailure("foreground_changed","Another window took the foreground. Remaining pointer input was cancelled.");
    }
    static void WaitPointerQuiet(IntPtr h){
        var wait=System.Diagnostics.Stopwatch.StartNew();
        do {
            CheckActivation(h);
            if(quiet.ElapsedMilliseconds>=120)return;
            System.Threading.Thread.Sleep(15);
        } while(wait.ElapsedMilliseconds<1000);
        throw GuardFailure("pointer_changed","Pointer movement did not settle before the action. No click was submitted.");
    }
    static bool SameGeometry(int[] a,int[] b){
        for(int i=0;i<4;i++)if(a[i]!=b[i])return false;
        return true;
    }
    static void RequireStableForeground(IntPtr h){
        int stable=0;
        int[] last=null;
        for(int i=0;i<45;i++){
            CheckActivation(h);
            // During a real Explorer restore, IsIconic can clear before the client
            // area reappears. This is a transition, not a new layout to click.
            var box=!IsIconic(h)&&TargetFront(h)?TryClientBounds(h):null;
            if(box!=null){
                bool original=initialBounds==null || (SameGeometry(initialBounds,box)&&GetDpiForWindow(h)==initialDpi&&State(h)==PointerStartingState);
                stable=original&&last!=null&&SameGeometry(last,box)?stable+1:0;
                if(stable>=3)return;
                last=box;
            } else {stable=0;last=null;}
            System.Threading.Thread.Sleep(20);
        }
        if(!TargetFront(h))throw new Exception("Windows did not grant foreground. Bring the selected window to the front and retry.");
        throw new Exception("Window layout or display scale changed during activation. Inspect again before clicking.");
    }
    public static void PreparePointer(IntPtr h,int x,int y,int clicks,string surface,int pid,string marker){
        pointerWindow=h;
        pointerRequested=clicks;
        pointerPid=pid;
        pointerMarker=marker;
        PointerStartingState=State(h);
        initialFront=GetAncestor(GetForegroundWindow(),2);
        hadTargetForeground=PointerStartingForeground=initialFront==h;
        ActivationMethod=PointerStartingForeground?"already_foreground":"set_foreground";
        initialInput=LastInput();
        if(!GetCursorPos(out initialCursor))throw new Exception("Cannot establish the starting pointer position.");
        initialBounds=IsIconic(h)?null:ClientBounds(h);
        initialDpi=GetDpiForWindow(h);
        WriteMouseReceipt("checking",0,false,false);
        try {
            StartInputGuard();
            WaitPointerQuiet(h);
            if(surface=="desktop"&&clicks==2&&!TargetFront(h)){
                // Explorer can receive a normal first click on an exposed icon even
                // while Windows keeps another top-level window as the foreground.
                CheckPointerForeground(h,true);
                var p=new Point{x=x,y=y};
                if(initialBounds==null||!SameGeometry(initialBounds,ClientBounds(h))||initialDpi!=GetDpiForWindow(h)||
                   x<0||y<0||x>=initialBounds[2]||y>=initialBounds[3]||!ClientToScreen(h,ref p))
                    throw new Exception("Desktop layout changed or point is outside the desktop client.");
                desktopIcon=ReadDesktopIcon(h,p,null);
                ActivationMethod="exposed_desktop_icon";
            } else AcquirePointerWindow(h,String.IsNullOrEmpty(surface));
        }
        catch(OperationCanceledException){WriteMouseReceipt("activation_cancelled",0,false,false);throw;}
        catch {WriteMouseReceipt("activation_stopped",0,false,false);throw;}
        readyBounds=ClientBounds(h);
        readyDpi=GetDpiForWindow(h);
        if(desktopIcon!=null&&(!SameGeometry(initialBounds,readyBounds)||initialDpi!=readyDpi))
            throw GuardFailure("desktop_layout_changed","Desktop geometry or display scale changed before positioning.");
        WriteMouseReceipt("ready_for_pointer",0,false,false);
    }
    static void AcquirePointerWindow(IntPtr h,bool allowCycle){
        CheckActivation(h);
        if(IsIconic(h)){
            ActivationMethod="restore";
            WriteMouseReceipt("restoring",0,true,false);
            WaitPointerQuiet(h);
            if(!ShowWindowAsync(h,9))throw new Exception("Windows did not queue the restore.");
            for(int i=0;i<45&&IsIconic(h);i++){CheckActivation(h);System.Threading.Thread.Sleep(20);}
            WriteMouseReceipt("after_restore",0,false,false);
            if(IsIconic(h))throw new Exception("Unable to restore target window.");
        }
        if(!TargetFront(h)){
            WriteMouseReceipt("activating",0,true,false);
            WaitPointerQuiet(h);
            bool accepted=SetForegroundWindow(h);
            for(int i=0;accepted&&i<12&&!TargetFront(h);i++){CheckActivation(h);System.Threading.Thread.Sleep(20);}
            WriteMouseReceipt("after_activation",0,false,false);
            if(!TargetFront(h)&&allowCycle&&initialBounds!=null&&(GetStyle(h,-16)&0x20000)!=0&&
               Class(h)!="Shell_TrayWnd"&&Class(h)!="Shell_SecondaryTrayWnd"&&Class(h)!="Progman"&&Class(h)!="WorkerW"){
                CheckActivation(h);
                ActivationMethod="minimize_restore";
                WriteMouseReceipt("activation_cycle",0,true,false);
                WaitPointerQuiet(h);
                // Queue the two show commands together so a cancellation cannot strand the target
                // between a timed minimize and a later restore. Neither command injects a click.
                if(!ShowWindowAsync(h,7))throw new Exception("Windows did not queue the temporary minimize.");
                ActivationCycleSubmitted=true;
                if(!ShowWindowAsync(h,9))throw new Exception("Windows did not queue the matching restore. Inspect the window state.");
                WriteMouseReceipt("activation_cycle_submitted",0,true,false);
            }
        }
        RequireStableForeground(h);
    }
    static bool MatchesDesktopItem(IAccessible parent,object child,DesktopIcon icon){
        IAccessible item=child as IAccessible;
        if(item==null)item=parent;else child=0;
        if(!String.Equals(item.get_accName(child),icon.name,StringComparison.Ordinal)||
           Convert.ToInt32(item.get_accRole(child))!=34)return false; // ROLE_SYSTEM_LISTITEM
        int x,y,w,h;item.accLocation(out x,out y,out w,out h,child);
        return SameGeometry(icon.bounds,new[]{x,y,w,h});
    }
    // Some Explorer accessibility providers return an item object (CHILDID_SELF)
    // instead of a positive list child ID. Pin its unique ordinal in the native
    // list; subsequent checks need to read only that one slot.
    static int DesktopItemOrdinal(IntPtr list,DesktopIcon icon,int expected){
        IAccessible parent;Guid iid=typeof(IAccessible).GUID;
        if(AccessibleObjectFromWindow(list,unchecked((uint)-4),ref iid,out parent)!=0||parent==null)return -1;
        int total=parent.accChildCount;
        if(total<1||expected>=total||(expected<0&&total>4096))return -1;
        int found=-1, end=expected<0?total:expected+1;
        for(int start=Math.Max(0,expected);start<end;){
            int count=Math.Min(64,end-start),actual;
            var children=new object[count];
            if(AccessibleChildren(parent,start,count,children,out actual)<0||actual!=count)return -1;
            for(int i=0;i<actual;i++){
                if(!MatchesDesktopItem(parent,children[i],icon))continue;
                if(found!=-1)return -1;
                found=start+i;
            }
            start+=actual;
        }
        return found;
    }
    static DesktopIcon ReadDesktopIcon(IntPtr root,Point p,DesktopIcon expected){
        IntPtr list=NativeDesktopList(root),owner;
        if(list==IntPtr.Zero||WindowFromPoint(p)!=list||GetAncestor(list,2)!=root)
            throw GuardFailure("desktop_icon_obscured","The point does not hit the exposed native desktop icon list.");
        IAccessible element;object child;
        if(AccessibleObjectFromPoint(p,out element,out child)!=0||element==null||!(child is int)||
           (int)child<0||WindowFromAccessibleObject(element,out owner)!=0||owner!=list||
           Convert.ToInt32(element.get_accRole(child))!=34)
            throw GuardFailure("desktop_icon_unverified","The desktop point does not identify a native icon.");
        int x,y,w,h;element.accLocation(out x,out y,out w,out h,child);
        string name=element.get_accName(child);
        if(String.IsNullOrEmpty(name)||w<=0||h<=0||p.x<x||p.y<y||p.x>=(long)x+w||p.y>=(long)y+h)
            throw GuardFailure("desktop_icon_unverified","The point is outside the named desktop icon.");
        var item=new DesktopIcon{list=list,childId=(int)child,name=name,bounds=new[]{x,y,w,h}};
        if(expected!=null&&(item.list!=expected.list||item.childId!=expected.childId||
           !String.Equals(item.name,expected.name,StringComparison.Ordinal)||!SameGeometry(item.bounds,expected.bounds)))
            throw GuardFailure("desktop_icon_changed","The desktop icon or its position changed.");
        if(item.childId==0||Convert.ToInt32(element.get_accRole(0))!=33){ // ROLE_SYSTEM_LIST
            item.ordinal=DesktopItemOrdinal(list,item,expected==null?-1:expected.ordinal);
            if(item.ordinal<0)throw GuardFailure("desktop_icon_unverified","Cannot identify the unique desktop icon within its list.");
        }
        if(expected!=null&&item.ordinal!=expected.ordinal)
            throw GuardFailure("desktop_icon_changed","The desktop icon changed its position within the list.");
        if(WindowFromPoint(p)!=list)
            throw GuardFailure("desktop_icon_obscured","The desktop icon became covered.");
        return item;
    }
    static Point ValidatePoint(IntPtr h,int x,int y){
        if(desktopIcon!=null)CheckPointerForeground(h,true);
        else if(!TargetFront(h))throw new Exception("Target is no longer the active window.");
        if(IsIconic(h)||!IsWindowEnabled(h))throw new Exception("The target is minimized or disabled.");
        var b=ClientBounds(h);
        if(!SameGeometry(readyBounds,b)||GetDpiForWindow(h)!=readyDpi)
            throw new Exception("Window layout or display scale changed. Inspect again before clicking.");
        if(x<0||y<0||x>=b[2]||y>=b[3])throw new Exception("Point outside the target client area.");
        var pt=new Point{x=x,y=y};
        if(!ClientToScreen(h,ref pt)||GetAncestor(WindowFromPoint(pt),2)!=h)
            throw new Exception("Point is obscured or belongs to a different window.");
        if(desktopIcon!=null){
            ReadDesktopIcon(h,pt,desktopIcon);
            CheckPointerForeground(h,true);
        }
        var info=new GuiThreadInfo();info.size=Marshal.SizeOf(typeof(GuiThreadInfo));
        if(!GetGUIThreadInfo(0,ref info)||info.capture!=IntPtr.Zero||info.menuOwner!=IntPtr.Zero||info.moveSize!=IntPtr.Zero)
            throw new Exception("A menu, mouse capture or window drag prevents safe pointer input.");
        foreach(int key in new[]{1,2,4,5,6,16,17,18,91,92})
            if((GetAsyncKeyState(key)&0x8000)!=0)throw new Exception("Release all mouse buttons and modifier keys before pointer input.");
        return pt;
    }
    static Point AtDestination(IntPtr h,int x,int y){
        var p=ValidatePoint(h,x,y); Point cursor;
        if(!GetCursorPos(out cursor))throw GuardFailure("position_unavailable","Cannot verify the pointer position.");
        if(cursor.x!=p.x||cursor.y!=p.y)
            throw GuardFailure("pointer_moved_after_position","Pointer moved after positioning; remaining clicks were cancelled.");
        return cursor;
    }
    static void WaitBetweenClicks(IntPtr h,long limit){
        int interval=(int)Math.Min(32,Math.Max(1,limit/8));
        if(desktopIcon==null){System.Threading.Thread.Sleep(interval);return;}
        // Explorer may assign focus as a consequence of the first button pair.
        // A transient null foreground may settle. A third-party foreground, or
        // losing the desktop once it gained focus, immediately ends the pair.
        var wait=System.Diagnostics.Stopwatch.StartNew();
        long settle=Math.Min(limit/3,90);
        do {
            CheckCancellation();
            CheckPointerForeground(h,false);
            if(wait.ElapsedMilliseconds>=interval&&GetForegroundWindow()!=IntPtr.Zero)return;
            System.Threading.Thread.Sleep(4);
        } while(wait.ElapsedMilliseconds<settle);
        CheckPointerForeground(h,true);
    }
    public class PointerResult {
        public int x, y, completed;
        public string detail="";
        public bool partial, incompletePair;
    }
    public static string CancelPath, ReceiptPath;
    public static void CheckCancellation(){
        if(!String.IsNullOrEmpty(CancelPath)&&System.IO.File.Exists(CancelPath))
            throw new OperationCanceledException("Desktop request was cancelled.");
    }
    public static void SavePointerInterruption(){
        if(readyBounds!=null&&GuardReason!="none")WriteMouseReceipt("input_yielded",0,false,false);
    }
    static IntPtr pointerWindow;
    static int pointerRequested;
    static bool positionSubmitted;
    public static string PointerStartingState;
    public static bool PointerStartingForeground;
    static string JsonBool(bool b){return b?"true":"false";}
    static void WriteMouseReceipt(string stage,int completed,bool uncertain,bool clickInFlight){
        if(String.IsNullOrEmpty(ReceiptPath))return;
        string state=IsWindow(pointerWindow)?State(pointerWindow):"closed";
        bool fg=TargetFront(pointerWindow);
        bool observed=state!=PointerStartingState||fg!=PointerStartingForeground||positionSubmitted||completed>0;
        bool finished=(stage=="positioned"&&pointerRequested==0)||(stage=="clicked"&&completed==pointerRequested);
        string status=finished?"completed":observed?"partial":uncertain||ActivationCycleSubmitted?"unknown":
            stage=="activation_cancelled"?"cancelled":"failed";
        string effect=observed?"observed":uncertain||ActivationCycleSubmitted?"possible":"none";
        string json="{\"status\":\""+status+"\",\"effect\":\""+effect+"\",\"stage\":\""+stage+
            "\",\"completed_clicks\":"+completed+",\"requested_clicks\":"+pointerRequested+
            ",\"click_in_flight\":"+JsonBool(clickInFlight)+",\"pointer_position_submitted\":"+JsonBool(positionSubmitted)+
            ",\"previous_state\":\""+PointerStartingState+"\",\"window_state\":\""+state+
            "\",\"foreground_before\":"+JsonBool(PointerStartingForeground)+",\"foreground_after\":"+JsonBool(fg)+
            ",\"activation_method\":\""+ActivationMethod+"\",\"desktop_icon_verified\":"+JsonBool(DesktopIconVerified)+",\"activation_cycle_submitted\":"+JsonBool(ActivationCycleSubmitted)+
            ",\"activation_guard\":\""+GuardReason+"\",\"pointer_changes_before_move\":"+PointerChanges+
            ",\"last_input_clock_changes\":"+InputClockChanges+"}";
        string tmp=ReceiptPath+".mouse";
        System.IO.File.WriteAllText(tmp,json,new System.Text.UTF8Encoding(false));
        if(System.IO.File.Exists(ReceiptPath))System.IO.File.Replace(tmp,ReceiptPath,null);
        else System.IO.File.Move(tmp,ReceiptPath);
    }
    public static PointerResult Pointer(IntPtr h,int x,int y,int clicks,int pid,string marker){
        if(clicks<0||clicks>2)throw new Exception("Expected zero, one or two clicks.");
        WaitPointerQuiet(h);
        var p=ValidatePoint(h,x,y);
        Point start;
        int animations;
        if(desktopIcon==null&&(clicks==0||PointerStartingForeground)&&GetCursorPos(out start) && GetAncestor(WindowFromPoint(start),2)==h &&
           GetAnimationSetting(0x1042,0,out animations,0) && animations!=0){
            double dx=(double)p.x-start.x, dy=(double)p.y-start.y;
            double distance=Math.Sqrt(dx*dx+dy*dy);
            if(distance>24){
                int steps=(int)Math.Min(13,Math.Max(6,distance/65));
                var last=start;
                for(int step=1;step<steps;step++){
                    Point current;
                    if(!GetCursorPos(out current)||current.x!=last.x||current.y!=last.y)
                        throw new Exception("Pointer was moved during the action.");
                    double t=(double)step/steps, eased=t*t*(3-2*t);
                    int sx=(int)Math.Round(start.x+dx*eased), sy=(int)Math.Round(start.y+dy*eased);
                    var way=new Point{x=sx,y=sy};
                    // Jump directly to the validated target if the path crosses a different window.
                    if(GetAncestor(WindowFromPoint(way),2)!=h)break;
                    var local=way;
                    if(!ScreenToClient(h,ref local))throw new Exception("Cannot translate the pointer path.");
                    var box=ClientBounds(h);
                    if(local.x<0||local.y<0||local.x>=box[2]||local.y>=box[3])break;
                    CheckCancellation();
                    var next=ValidatePoint(h,local.x,local.y);
                    if(next.x!=sx||next.y!=sy)
                        throw new Exception("Target moved during the pointer action.");
                    SubmitPosition(sx,sy);
                    last=way;
                    System.Threading.Thread.Sleep(16);
                }
                Point reached;
                if(!GetCursorPos(out reached)||reached.x!=last.x||reached.y!=last.y)
                    throw new Exception("Pointer was moved during the action.");
            }
        }
        p=ValidatePoint(h,x,y);
        CheckCancellation();
        SubmitPosition(p.x,p.y);
        System.Threading.Thread.Sleep(35);
        var final=AtDestination(h,x,y);
        WriteMouseReceipt("positioned",0,false,false);
        var result=new PointerResult{x=final.x,y=final.y};
        if(clicks==0)return result;
        var receiver=WindowFromPoint(final);
        var events=new[]{new Input{mouse=new MouseInput{flags=2}},new Input{mouse=new MouseInput{flags=4}}};
        int size=Marshal.SizeOf(typeof(Input));
        long limit=GetDoubleClickTime();
        var clock=new System.Diagnostics.Stopwatch();
        for(int index=0;index<clicks;index++){
            try {
                if(index!=0)WaitBetweenClicks(h,limit);
                var at=AtDestination(h,x,y);
                if(Pid(h)!=pid || (!String.IsNullOrEmpty(marker)&&Title(h).IndexOf(marker,StringComparison.Ordinal)<0))
                    throw new Exception("Bound application or selected document changed.");
                if(at.x!=final.x||at.y!=final.y||WindowFromPoint(at)!=receiver)
                    throw new Exception("Mouse receiver changed. Remaining click was cancelled.");
                WriteMouseReceipt("submitting_click",result.completed,true,true);
                CheckCancellation();
                if(desktopIcon!=null)AtDestination(h,x,y);
                if(index==0){CheckPhysicalInput();EndInputGuard();}
                CheckCancellation();
                if(index==0)clock.Start();
                else if(clock.ElapsedMilliseconds>=limit)throw new Exception("System double-click interval elapsed.");
                uint count=SendInput(2,events,size);
                if(count==1){
                    SendInput(1,new[]{events[1]},size);
                    result.partial=true;
                    result.incompletePair=true;
                    WriteMouseReceipt("button_pair_incomplete",result.completed,true,true);
                    throw new Exception("Only a button-down was confirmed. A release was attempted; inspect before retrying.");
                }
                if(count!=2)throw new Exception("Windows blocked the click.");
                result.completed++;
                WriteMouseReceipt("clicked",result.completed,false,false);
            } catch(Exception error){
                if(!result.partial)WriteMouseReceipt("click_stopped",result.completed,false,false);
                if(result.completed==0&&!result.partial)throw;
                result.partial=true;
                result.detail=error.Message;
                break;
            }
        }
        return result;
    }
    static void SubmitPosition(int x,int y){
        if(!positionSubmitted)WriteMouseReceipt("submitting_position",0,true,false);
        CheckCancellation();
        if(!positionSubmitted)WaitPointerQuiet(pointerWindow);else CheckPhysicalInput();
        if(!SetCursorPos(x,y))throw new Exception("Windows did not move the pointer.");
        if(!positionSubmitted){
            positionSubmitted=true;
            WriteMouseReceipt("positioning",0,false,false);
        }
    }
    public static long[] Windows(long parent) {
        var list=new List<long>(); EnumProc cb=(h,p)=>{if(IsWindowVisible(h))list.Add(h.ToInt64());return true;};
        if(parent==0)EnumWindows(cb,IntPtr.Zero); else EnumChildWindows(new IntPtr(parent),cb,IntPtr.Zero);
        return list.ToArray();
    }
    public static int Pid(IntPtr h){uint pid;GetWindowThreadProcessId(h,out pid);return (int)pid;}
    public static string Title(IntPtr h){var b=new StringBuilder(2048);GetWindowText(h,b,b.Capacity);return b.ToString();}
    public static string Class(IntPtr h){var b=new StringBuilder(256);GetClassName(h,b,b.Capacity);return b.ToString();}
    static IntPtr NativeDesktopList(IntPtr h){
        var shell=GetShellWindow();
        if(shell==IntPtr.Zero||!IsWindowVisible(h)||Pid(h)!=Pid(shell)||
           (Class(h)!="Progman"&&Class(h)!="WorkerW"))return IntPtr.Zero;
        var view=FindWindowEx(h,IntPtr.Zero,"SHELLDLL_DefView",null);
        if(view==IntPtr.Zero||Pid(view)!=Pid(shell)||!IsWindowVisible(view))return IntPtr.Zero;
        var icons=FindWindowEx(view,IntPtr.Zero,"SysListView32",null);
        return icons!=IntPtr.Zero&&IsWindowVisible(icons)&&Pid(icons)==Pid(shell)?icons:IntPtr.Zero;
    }
    public static bool IsShellSurface(IntPtr h,string kind){
        if(kind=="desktop")return NativeDesktopList(h)!=IntPtr.Zero;
        var shell=GetShellWindow();
        return kind=="taskbar"&&shell!=IntPtr.Zero&&IsWindowVisible(h)&&Pid(h)==Pid(shell)&&Class(h)=="Shell_TrayWnd";
    }
    static IntPtr Send(IntPtr h,uint m,IntPtr w,IntPtr l){
        IntPtr result; if(Msg(h,m,w,l,2,2000,out result)==IntPtr.Zero)throw new Exception("Target did not accept the window message.");
        return result;
    }
    public static string Read(IntPtr e){
        long n=Send(e,0x000E,IntPtr.Zero,IntPtr.Zero).ToInt64();
        int limit=Class(e).StartsWith("RichEdit",StringComparison.OrdinalIgnoreCase)?65534:100000;
        if(n<0||n>limit)throw new Exception("Editor text exceeds its supported UTF-16 read limit.");
        var buf=Marshal.AllocHGlobal((int)(n+1)*2);
        try {int actual=Send(e,0x000D,new IntPtr(n+1),buf).ToInt32();
            if(actual<0||actual>n||Send(e,0x000E,IntPtr.Zero,IntPtr.Zero).ToInt64()!=n)
                throw new Exception("Editor changed during read.");
            return Marshal.PtrToStringUni(buf,actual);}
        finally {Marshal.FreeHGlobal(buf);}
    }
    public static int[] Selection(IntPtr e) {
        IntPtr start=Marshal.AllocHGlobal(4), end=Marshal.AllocHGlobal(4);
        try {Marshal.WriteInt32(start,-1);Marshal.WriteInt32(end,-1);Send(e,0x00B0,start,end);
             return new[]{Marshal.ReadInt32(start),Marshal.ReadInt32(end)};}
        finally {Marshal.FreeHGlobal(start);Marshal.FreeHGlobal(end);}
    }
    static void CheckNativeEditor(IntPtr root,IntPtr e,bool focused) {
        var cls=Class(e);
        if(GetAncestor(e,2)!=root||!IsWindowEnabled(root)||!IsWindowEnabled(e)||!IsWindowVisible(e)||
           !(cls.Equals("Edit",StringComparison.OrdinalIgnoreCase)||cls.StartsWith("RichEdit",StringComparison.OrdinalIgnoreCase))||
           (GetStyle(e,-16)&0x820)!=0)throw new Exception("The selected native editor changed or is protected.");
        if(focused){
            var info=new GuiThreadInfo();info.size=Marshal.SizeOf(typeof(GuiThreadInfo));
            if(!ActiveInputWindow(root)||!GetGUIThreadInfo(0,ref info)||info.focus!=e)
                throw new Exception("The selected native field lost keyboard focus.");
        }
    }
    public static void Insert(IntPtr root,IntPtr e,string text,bool append){
        var p=Marshal.StringToHGlobalUni(text);
        try{
            CheckCancellation();
            CheckNativeEditor(root,e,!append);
            if(append){
                int len=Send(e,0x000E,IntPtr.Zero,IntPtr.Zero).ToInt32();
                Send(e,0x00B1,new IntPtr(len),new IntPtr(len));
            }
            CheckCancellation();
            CheckNativeEditor(root,e,!append);
            Send(e,0x00C2,new IntPtr(1),p);
        } finally {Marshal.FreeHGlobal(p);}
    }
    public static bool ActiveInputWindow(IntPtr h) {
        var info=new GuiThreadInfo();info.size=Marshal.SizeOf(typeof(GuiThreadInfo));
        return TargetFront(h) && IsWindowEnabled(h) && !IsIconic(h) && GetGUIThreadInfo(0,ref info)
               && info.focus!=IntPtr.Zero && GetAncestor(info.focus,2)==h
               && info.capture==IntPtr.Zero && info.menuOwner==IntPtr.Zero && info.moveSize==IntPtr.Zero;
    }
    [StructLayout(LayoutKind.Sequential)] struct KeyInput {public ushort vk,scan;public uint flags,time;public UIntPtr extra;}
    [StructLayout(LayoutKind.Explicit)] struct InputPayload {
        [FieldOffset(0)] public KeyInput key;
        [FieldOffset(0)] public MouseInput accessForLayout;
    }
    [StructLayout(LayoutKind.Sequential)] struct KeyEvent {public uint type;public InputPayload payload;}
    [DllImport("user32.dll",EntryPoint="SendInput")] static extern uint SendKeysNative(uint count, KeyEvent[] data,int size);
    static KeyEvent Key(ushort vk,ushort scan,uint flags) {
        return new KeyEvent{type=1,payload=new InputPayload{key=new KeyInput{vk=vk,scan=scan,flags=flags}}};
    }
    static void SendKeysTo(IntPtr h,KeyEvent[] events) {
        CheckCancellation();
        if(!ActiveInputWindow(h))throw new Exception("Selected window lost focus or a menu is active.");
        foreach(int key in new[]{1,2,4,5,6,16,17,18,91,92})
            if((GetAsyncKeyState(key)&0x8000)!=0)throw new Exception("Release mouse buttons and modifier keys first.");
        int size=Marshal.SizeOf(typeof(KeyEvent));
        var delivered=SendKeysNative((uint)events.Length,events,size);
        if(delivered!=events.Length) {
            if(delivered>0) {
                var held=new List<KeyEvent>();
                for(int i=0;i<(int)delivered;i++){
                    var key=events[i].payload.key;
                    if((key.flags&2)==0)held.Add(Key(key.vk,key.scan,key.flags|2));
                    else held.RemoveAll(v=>v.payload.key.vk==key.vk&&v.payload.key.scan==key.scan);
                }
                held.Reverse();if(held.Count>0)SendKeysNative((uint)held.Count,held.ToArray(),size);
            }
            throw new Exception("Windows did not accept the complete keyboard operation.");
        }
    }
    public static void Shortcut(IntPtr h,string key) {
        if(key=="Ctrl+L")SendKeysTo(h,new[]{Key(17,0,0),Key(76,0,0),Key(76,0,2),Key(17,0,2)});
        else if(key=="Enter")SendKeysTo(h,new[]{Key(13,0,0),Key(13,0,2)});
        else throw new Exception("Unsupported shortcut.");
    }
    public static void UnicodeInput(IntPtr h,string text) {
        var events=new KeyEvent[text.Length*2];
        for(int i=0;i<text.Length;i++){events[2*i]=Key(0,text[i],4);events[2*i+1]=Key(0,text[i],6);}
        SendKeysTo(h,events);
    }
}
'@
}

function Find-Target([string]$name,[string]$title,[switch]$Partial) {
    $ids = @(Get-Process -Name $name -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
    foreach($handle in [WBWin]::Windows(0)){
        $h = [IntPtr]::new($handle)
        if ($ids -notcontains [WBWin]::Pid($h)) {continue}
        $s = [WBWin]::Title($h)
        if (($Partial -and $s.Contains($title)) -or ((-not $Partial) -and $s -ceq $title)) {$handle}
    }
}

function Bind-Target([long]$handle,[string]$marker) {
    $h = [IntPtr]::new($handle)
    $proc = Get-Process -Id ([WBWin]::Pid($h))
    $b = @{hwnd=$handle; process=$proc.Id; start=$proc.StartTime.ToUniversalTime().Ticks.ToString(); marker=$marker}
    return @{binding=$b; title=[WBWin]::Title($h); process=$proc.ProcessName}
}

function Confirm-Target($binding) {
    $h = [IntPtr]::new([long]$binding.hwnd)
    if (-not [WBWin]::IsWindowVisible($h) -or [WBWin]::Pid($h) -ne $binding.process) {throw 'Selected window is no longer available.'}
    $proc = Get-Process -Id $binding.process
    if ($proc.StartTime.ToUniversalTime().Ticks.ToString() -ne $binding.start) {throw 'Window process changed.'}
    if ($binding.shell_surface -and ![WBWin]::IsShellSurface($h,$binding.shell_surface)) {throw 'Windows Shell surface changed. Select it again.'}
    if ($binding.marker -and -not [WBWin]::Title($h).Contains($binding.marker)) {throw 'Selected Notepad tab changed. Switch back to the document created for this task.'}
    return $h
}

function Test-Same([string]$a,[string]$b) {
    return [string]::Equals($a,$b,[StringComparison]::Ordinal)
}

function Get-WindowTree([IntPtr]$h) {
    $root=[System.Windows.Automation.AutomationElement]::FromHandle($h)
    if (!$root) {throw 'Unable to access window controls.'}
    $walker=[System.Windows.Automation.TreeWalker]::ControlViewWalker
    $queue=New-Object System.Collections.Queue
    $items=New-Object System.Collections.ArrayList
    $page=New-Object 'System.Collections.Generic.List[string]'
    $processName=(Get-Process -Id ([WBWin]::Pid($h))).ProcessName
    $browser=$processName -in @('chrome','msedge','chromium','brave','vivaldi','opera')
    $clock=[Diagnostics.Stopwatch]::StartNew()
    $cut=$false
    $queue.Enqueue($root)
    while ($queue.Count -and !$cut) {
        Assert-DesktopActive
        $parent=$queue.Dequeue()
        $el=$walker.GetFirstChild($parent)
        while ($null -ne $el) {
            if ($items.Count -ge 320 -or $clock.Elapsed.TotalMilliseconds -gt 2600) {$cut=$true; break}
            $cur=$el.Current
            # Password controls, including their descendants, never contribute names or text.
            if (!$cur.IsPassword -and !$cur.IsOffscreen) {
                [void]$items.Add($el)
                $queue.Enqueue($el)
                if ($browser -and $cur.ControlType -eq [System.Windows.Automation.ControlType]::Document) {
                    $page.Add('d:' + ($el.GetRuntimeId() -join '.') + ':' + $cur.Name)
                } elseif ($cur.ControlType -eq [System.Windows.Automation.ControlType]::TabItem) {
                    $sel=$null
                    if ($el.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern,[ref]$sel) -and $sel.Current.IsSelected) {
                        $page.Add('t:' + ($el.GetRuntimeId() -join '.'))
                    }
                }
            }
            $el=$walker.GetNextSibling($el)
        }
    }
    $title=[WBWin]::Title($h)
    # Notepad's leading dirty marker changes on typing into the very same document.
    if ($processName -eq 'notepad') {$title=$title.TrimStart([char]'*')}
    $context=$title+'|'+($page -join '|')
    return @{items=$items; truncated=$cut; browser=$browser; page_known=(!$browser -or $page.Count -gt 0); context=$context}
}

function Get-ElementId([IntPtr]$h,$el,$tree) {
    $identity=@($h.ToInt64(),$tree.context,($el.GetRuntimeId() -join '.'),$el.Current.AutomationId,$el.Current.ControlType.Id)
    $encoded=ConvertTo-Json -Compress -InputObject $identity
    $hash=[Security.Cryptography.SHA256]::Create()
    try {return [BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($encoded))).Replace('-','').ToLowerInvariant()}
    finally {$hash.Dispose()}
}

function Get-EditorInfo($el) {
    $cur=$el.Current
    $role=$cur.ControlType
    if (!$cur.IsEnabled -or $cur.IsOffscreen -or $cur.IsPassword -or
        ($role -ne [System.Windows.Automation.ControlType]::Edit -and $role -ne [System.Windows.Automation.ControlType]::Document)) {return}
    $hwnd=[IntPtr]::new($cur.NativeWindowHandle)
    $class=if($hwnd -ne [IntPtr]::Zero){[WBWin]::Class($hwnd)}else{''}
    if ($class -match '^(Edit|RichEdit.*)$') {
        $style=[WBWin]::GetStyle($hwnd,-16)
        if (($style -band 0x20) -or ![WBWin]::IsWindowEnabled($hwnd) -or ![WBWin]::IsWindowVisible($hwnd)) {return}
        $limit=if($class -match '^RichEdit'){65534}else{100000}
        return @{source='Win32'; control=$hwnd; element=$el; writable=!($style -band 0x800); limit=$limit}
    }
    # A generic browser Document exposes the text of the page, not a single form field.
    if ($role -ne [System.Windows.Automation.ControlType]::Edit) {return}
    $val=$null
    $txt=$null
    $hasValue=$el.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern,[ref]$val)
    $hasText=$el.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern,[ref]$txt)
    if (!$hasValue -and !$hasText) {return}
    return @{source='UIAutomation'; control=$el; element=$el; value_pattern=$val; text_pattern=$txt
             writable=($hasValue -and !$val.Current.IsReadOnly -and $cur.IsKeyboardFocusable); limit=100000}
}

function Get-FocusedControl([IntPtr]$h) {
    if (![WBWin]::ActiveInputWindow($h)) {throw 'The selected window must be in the foreground with an active input focus.'}
    $focused=[System.Windows.Automation.AutomationElement]::FocusedElement
    if (!$focused -or !$focused.Current.IsEnabled -or $focused.Current.IsOffscreen) {throw 'No visible enabled input focus.'}
    $root=[System.Windows.Automation.AutomationElement]::FromHandle($h)
    $walker=[System.Windows.Automation.TreeWalker]::RawViewWalker
    $parent=$focused
    for ($i=0;$null -ne $parent -and $i -lt 64;$i++) {
        if ($parent.Current.IsPassword) {throw 'Password fields cannot be targeted.'}
        if ([System.Windows.Automation.Automation]::Compare($root,$parent)) {return $focused}
        $parent=$walker.GetParent($parent)
    }
    throw 'The focused element is outside the selected window.'
}

function Get-Editor([IntPtr]$h,$req=$null) {
    if (![WBWin]::IsWindowEnabled($h)) {throw 'The selected window is disabled or modal.'}
    $tree=Get-WindowTree $h
    $editors=New-Object System.Collections.ArrayList
    if ($req.target -eq 'focused') {
        $el=Get-FocusedControl $h
        $info=Get-EditorInfo $el
        if (!$info) {throw 'The focused element is not a supported nonpassword editor.'}
    } else {
        foreach($el in $tree.items) {
            $item=Get-EditorInfo $el
            if (!$item) {continue}
            if ($req.element_id) {
                if ((Get-ElementId $h $el $tree) -ceq $req.element_id) {[void]$editors.Add($item)}
            } else {[void]$editors.Add($item)}
        }
        if ($tree.truncated -and !$req.element_id) {throw 'The control scan was truncated; specify a verified element_id or target=focused.'}
        if ($editors.Count -ne 1) {throw 'Expected one matching editor. Inspect again and choose element_id or target=focused.'}
        $info=$editors[0]
    }
    if (!$tree.page_known) {throw 'Cannot verify the active browser document or tab. Inspect again after the page settles.'}
    $info.id=Get-ElementId $h $info.element $tree
    return $info
}

function Read-Editor($editor) {
    if ($editor.source -eq 'Win32') {$value=[WBWin]::Read($editor.control)}
    elseif ($editor.value_pattern) {$value=$editor.value_pattern.Current.Value}
    else {$value=$editor.text_pattern.DocumentRange.GetText($editor.limit+1)}
    if ($value.Length -gt $editor.limit) {throw 'Editor text exceeds its supported UTF-16 read limit.'}
    return [string]$value
}

function Get-FieldSelection($editor,[string]$value) {
    if ($editor.source -eq 'Win32') {
        $range=[WBWin]::Selection($editor.control)
        if ($range[0] -lt 0 -or $range[1] -lt $range[0] -or $range[1] -gt $value.Length) {throw 'Cannot verify native text selection.'}
        # Rich Edit may use single-character paragraph indices while WM_GETTEXT returns CRLF.
        if ($value.Contains([char]13) -and [WBWin]::Class($editor.control) -match '^RichEdit') {throw 'Focused replacement in multiline Rich Edit is unsupported; use append instead.'}
        return @{before=$value.Substring(0,$range[0]);after=$value.Substring($range[1])}
    }
    if ($value.Length -eq 0) {return @{before='';after=''}}
    $pt=$editor.text_pattern
    if (!$pt) {throw 'This field does not expose a verifiable selection.'}
    $ranges=$pt.GetSelection()
    if ($ranges.Length -ne 1) {throw 'A single verifiable selection is required.'}
    $doc=$pt.DocumentRange
    $before=$doc.Clone(); $after=$doc.Clone()
    $start=[System.Windows.Automation.Text.TextPatternRangeEndpoint]::Start
    $end=[System.Windows.Automation.Text.TextPatternRangeEndpoint]::End
    $before.MoveEndpointByRange($end,$ranges[0],$start)
    $after.MoveEndpointByRange($start,$ranges[0],$end)
    $prefix=[string]$before.GetText(100001)
    $suffix=[string]$after.GetText(100001)
    $selected=[string]$ranges[0].GetText(100001)
    if (!(Test-Same ($prefix+$selected+$suffix) $value)) {throw 'Text selection and field value disagree; no typing was issued.'}
    return @{before=$prefix;after=$suffix}
}

function Confirm-Editor($h,$req,$editor) {
    [void](Confirm-Target $req.binding)
    $now=Get-Editor $h $req
    if (!(Test-Same $editor.id $now.id)) {throw 'The active document or target field changed.'}
    return $now
}

function Write-Editor($h,$req,$editor,[string]$value) {
    $incoming=[string]$req.text
    if (!$editor.writable) {throw 'The target is read-only or does not expose a safe editing method.'}
    if ($incoming.Length -gt 10000 -or $incoming.Contains([char]0)) {throw 'Input must contain at most 10000 UTF-16 units and no NUL.'}
    $focused=$req.target -eq 'focused'
    $range=if($focused){Get-FieldSelection $editor $value}else{@{before=$value;after=''}}
    $expected=$range.before+$incoming+$range.after
    if ($expected.Length -gt $editor.limit) {throw 'The result would exceed the supported readback limit for this field.'}
    if ($editor.source -eq 'UIAutomation') {
        if ($incoming -match '[\x00-\x1f\x7f]') {throw 'This virtual editor supports printable text only. Use desktop_press_key for its supported shortcuts.'}
        if (![WBWin]::ActiveInputWindow($h)) {throw 'The target window must already be in the foreground to type into a virtual editor.'}
        if (!$focused -and $value.Length -gt 0 -and !$editor.text_pattern) {throw 'This editor does not expose a verifiable end-of-text selection.'}
    }
    # Resolve again just before changing the selection or delivering input.
    $editor=Confirm-Editor $h $req $editor
    if (!$editor.writable -or !(Test-Same (Read-Editor $editor) $value)) {throw 'The field changed before typing.'}
    if ($editor.source -eq 'UIAutomation') {
        if (![System.Windows.Automation.Automation]::Compare((Get-FocusedControl $h),$editor.element)) {
            if ($focused) {throw 'The requested field lost focus.'}
            Start-DesktopEffect
            $editor.element.SetFocus()
        }
        if (!$focused -and $value.Length -gt 0) {
            if (![System.Windows.Automation.Automation]::Compare((Get-FocusedControl $h),$editor.element)) {throw 'Cannot confirm focus on the requested field.'}
            $endRange=$editor.text_pattern.DocumentRange.Clone()
            $endRange.MoveEndpointByRange([System.Windows.Automation.Text.TextPatternRangeEndpoint]::Start,$endRange,[System.Windows.Automation.Text.TextPatternRangeEndpoint]::End)
            Start-DesktopEffect
            $endRange.Select()
        }
        if (![System.Windows.Automation.Automation]::Compare((Get-FocusedControl $h),$editor.element)) {throw 'Target field lost focus before input.'}
    }
    if ($focused -or $editor.source -eq 'UIAutomation') {
        $selection=Get-FieldSelection $editor $value
        if (!(Test-Same $range.before $selection.before) -or !(Test-Same $range.after $selection.after)) {throw 'The selection changed before typing.'}
    }
    if (!(Test-Same (Read-Editor $editor) $value)) {throw 'The field changed immediately before typing.'}
    $result=@{status='unknown'; requested=$incoming.Length; entered=$null; verified=$false; units='utf16'; source=$editor.source; element_id=$editor.id}
    if (!$incoming.Length) {throw 'Input text must not be empty.'}
    [void](Confirm-Target $req.binding)
    Start-DesktopEffect
    try {
        if ($editor.source -eq 'Win32') {[WBWin]::Insert($h,$editor.control,$incoming,(!$focused))}
        else {[WBWin]::UnicodeInput($h,$incoming)}
    } catch {$result.detail='The input call did not complete. Read the field before deciding on another action.'}
    try {
        $deadline=[Diagnostics.Stopwatch]::StartNew()
        do {
            Assert-DesktopActive
            $observed=Read-Editor $editor
            if ((Test-Same $observed $expected) -or $deadline.ElapsedMilliseconds -ge 650) {break}
            Start-Sleep -Milliseconds 40
        } while ($true)
        $editor=Confirm-Editor $h $req $editor
        $observed=Read-Editor $editor
        if (Test-Same $observed $expected) {
            $result.status='completed'; $result.entered=$incoming.Length; $result.verified=$true
            [void]$result.Remove('detail')
        } elseif ($observed.Length -ge $range.before.Length+$range.after.Length -and
                  $observed.StartsWith($range.before,[StringComparison]::Ordinal) -and
                  $observed.EndsWith($range.after,[StringComparison]::Ordinal)) {
            $middle=$observed.Substring($range.before.Length,$observed.Length-$range.before.Length-$range.after.Length)
            if ($incoming.StartsWith($middle,[StringComparison]::Ordinal)) {
                $result.status='partial'; $result.entered=$middle.Length; $result.verified=$true
            }
        }
    } catch {}
    if ($result.status -ne 'completed') {$result.detail='The requested text was not fully confirmed. Read the field before deciding on another action.'}
    Set-DesktopReceipt $result
    return $result
}

function Open-NewNotepad {
    # A unique empty file names the new document, even if Notepad redirects its process to an existing frame.
    # Its path is used solely to select that tab. No input text or readback ever uses the file.
    $stem='WorkBuddy-'+[Guid]::NewGuid().ToString('N').Substring(0,12)
    $dir=Join-Path ([IO.Path]::GetTempPath()) 'WorkBuddy-Desktop'
    [void][IO.Directory]::CreateDirectory($dir)
    $path=Join-Path $dir ($stem+'.txt')
    Start-DesktopEffect
    $empty=[IO.File]::Open($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    $empty.Dispose()
    $exe=Join-Path $env:SystemRoot 'System32\notepad.exe'
    Assert-DesktopActive
    [void][Diagnostics.Process]::Start($exe,('"'+$path+'"'))
    $clock=[Diagnostics.Stopwatch]::StartNew()
    do {
        Start-Sleep -Milliseconds 200
        $candidates=@(Find-Target 'notepad' $stem -Partial)
        if ($candidates.Count -eq 1) {
            try {
                $editor=Get-Editor ([IntPtr]::new([long]$candidates[0]))
                $initial=[string](Read-Editor $editor)
                if ($initial.TrimEnd([char]13,[char]10).Length -eq 0) {return Bind-Target $candidates[0] $stem}
            } catch { $last=$_.Exception.Message }
        }
    } while ($clock.Elapsed.TotalSeconds -lt 10)
    throw "Could not verify a unique new empty Notepad document. $last"
}

function Invoke-Desktop($req){
    if ($req.action -eq 'desktop_open_notepad') {return Open-NewNotepad}
    if ($req.action -eq 'desktop_select_window') {
        if ($req.process_name -notmatch '^[\p{L}\w .-]{1,128}$') {throw 'Invalid process name.'}
        $processName=[string]$req.process_name -replace '(?i)\.exe$',''
        if ($processName -ieq 'explorer') {
            $surface=$null
            if ($req.exact_title -cin 'Windows Desktop',([regex]::Unescape('Windows \u684c\u9762'))) {$surface='desktop'}
            if ($req.exact_title -cin 'Windows Primary Taskbar',([regex]::Unescape('Windows \u4e3b\u4efb\u52a1\u680f'))) {$surface='taskbar'}
            if ($surface) {
                $matches=@(foreach($id in [WBWin]::Windows(0)) {
                    if ([WBWin]::IsShellSurface([IntPtr]::new([long]$id),$surface)) {$id}
                })
                if ($matches.Count -ne 1) {throw 'Exactly one matching Windows Explorer Shell surface is required.'}
                $selected=Bind-Target $matches[0] ''
                if ($selected.process -ine 'explorer') {throw 'Unexpected Windows shell process.'}
                $selected.binding.shell_surface=$surface
                $selected.surface=$surface
                $selected.title=$req.exact_title
                return $selected
            }
        }
        $handles=@(Find-Target $processName $req.exact_title)
        if ($handles.Count -ne 1) {throw 'Exactly one matching visible window is required.'}
        return Bind-Target $handles[0] ''
    }
    $h=Confirm-Target $req.binding
    if ($req.binding.shell_surface -eq 'taskbar' -and $req.action -notin 'desktop_inspect','desktop_invoke') {
        throw 'Use inspect and invoke an exactly named button on the selected taskbar. For an application window, use its own window binding.'
    }
    if ($req.binding.shell_surface -eq 'desktop' -and $req.action -notin 'desktop_inspect','desktop_move_mouse','desktop_click') {
        throw 'The selected desktop icons support inspect and scoped pointer actions.'
    }
    if ($req.action -eq 'desktop_window_state') {
        $action=[string]$req.state_action
        if ($action -cnotin 'query','restore','maximize','minimize') {throw 'Invalid window state action.'}
        $previous=[WBWin]::State($h)
        if ($action -ne 'query') {Start-DesktopEffect}
        $state=[WBWin]::ChangeState($h,$action)
        $result=@{action=$action; state=$state; window_state=$state; previous_state=$previous; status='completed'; verified=$true}
        if ($action -ne 'query') {Set-DesktopReceipt $result}
        return $result
    }
    if ($req.action -eq 'desktop_inspect' -and [WBWin]::State($h) -eq 'minimized') {
        return @{title=[WBWin]::Title($h); state='minimized'; window_state='minimized'; status='completed'; client=$null; controls=@();
                 detail='Window is minimized. Restore it and inspect again for current client coordinates.'}
    }
    if ($req.action -in 'desktop_move_mouse','desktop_click') {
        foreach ($coordinate in @($req.x,$req.y)) {
            if (($coordinate -isnot [int] -and $coordinate -isnot [long]) -or $coordinate -lt 0 -or $coordinate -gt [int]::MaxValue) {
                throw 'x and y must be nonnegative integers in target client pixels.'
            }
        }
        $clicks=0
        if ($req.action -eq 'desktop_click') {
            $clicks=1
            if ($null -ne $req.click_count) {
                if (($req.click_count -isnot [int] -and $req.click_count -isnot [long]) -or $req.click_count -notin 1,2) {
                    throw 'click_count must be the integer 1 or 2.'
                }
                $clicks=[int]$req.click_count
            }
        }
        [WBWin]::PhysicalCoordinates()
        Start-DesktopEffect
        try {
            [WBWin]::PreparePointer($h,[int]$req.x,[int]$req.y,$clicks,[string]$req.binding.shell_surface,[int]$req.binding.process,[string]$req.binding.marker)
            [void](Confirm-Target $req.binding)
            Assert-DesktopActive
            $point=[WBWin]::Pointer($h,[int]$req.x,[int]$req.y,$clicks,[int]$req.binding.process,[string]$req.binding.marker)
        } catch {[WBWin]::SavePointerInterruption(); throw}
        finally {[WBWin]::EndInputGuard()}
        $operation=@('move','left_click','left_double_click')[$clicks]
        $status=if($point.partial){'partial'}else{'completed'}
        $result=@{action=$operation; coordinate_system='client_physical_pixels'; client=@{x=$req.x;y=$req.y};
                  screen=@{x=$point.x;y=$point.y}; requested_clicks=$clicks; completed_clicks=$point.completed;
                  previous_state=[WBWin]::PointerStartingState; window_state=$(if([WBWin]::IsWindow($h)){[WBWin]::State($h)}else{'closed'});
                  foreground_before=[WBWin]::PointerStartingForeground; foreground_after=[WBWin]::TargetFront($h);
                  activation_method=[WBWin]::ActivationMethod; desktop_icon_verified=[WBWin]::DesktopIconVerified; activation_cycle_submitted=[WBWin]::ActivationCycleSubmitted;
                  activation_guard=[WBWin]::GuardReason; pointer_changes_before_move=[WBWin]::PointerChanges; last_input_clock_changes=[WBWin]::InputClockChanges;
                  click_in_flight=$point.incompletePair; status=$status; verified=(!$point.partial)}
        if($point.detail){$result.detail=$point.detail}
        Set-DesktopReceipt $result
        return $result
    }
    if ($req.action -eq 'desktop_inspect') {
        [WBWin]::PhysicalCoordinates()
        $box=[WBWin]::ClientBounds($h)
        $tree=Get-WindowTree $h
        $rows=@($tree.items | Select-Object -First 120 | ForEach-Object {
            $current=$_.Current
            $name=[string]$current.Name
            $nameCut=$name.Length -gt 180
            if ($nameCut) {$end=180; if ([char]::IsHighSurrogate($name[$end-1])) {$end--}; $name=$name.Substring(0,$end)}
            $info=Get-EditorInfo $_
            $row=@{role=$current.ControlType.ProgrammaticName; name=$name; name_truncated=$nameCut; enabled=$current.IsEnabled;
                   focused=$current.HasKeyboardFocus; can_read=($null -ne $info); can_write=($null -ne $info -and $info.writable)}
            if ($tree.page_known) {$row.element_id=Get-ElementId $h $_ $tree}
            $rect=$current.BoundingRectangle
            if (!$rect.IsEmpty -and $rect.Width -gt 0 -and $rect.Height -gt 0) {
                # Use the visible portion of each UIA physical screen rectangle inside this client.
                $left=[Math]::Max(0.0,$rect.Left-$box[0])
                $right=[Math]::Min([double]$box[2],$rect.Right-$box[0])
                $top=[Math]::Max(0.0,$rect.Top-$box[1])
                $bottom=[Math]::Min([double]$box[3],$rect.Bottom-$box[1])
                if ($left -lt $right -and $top -lt $bottom) {
                    $pixelLeft=[int][Math]::Ceiling($left)
                    $pixelRight=[int][Math]::Ceiling($right)
                    $pixelTop=[int][Math]::Ceiling($top)
                    $pixelBottom=[int][Math]::Ceiling($bottom)
                    if ($pixelLeft -lt $pixelRight -and $pixelTop -lt $pixelBottom) {
                        $row.bounds=@{left=$pixelLeft;top=$pixelTop;right=$pixelRight;bottom=$pixelBottom}
                        $row.center=@{x=[int][Math]::Floor(($pixelLeft+$pixelRight)/2);y=[int][Math]::Floor(($pixelTop+$pixelBottom)/2)}
                    }
                }
            }
            $row
        })
        [void](Confirm-Target $req.binding)
        $state=[WBWin]::State($h)
        return @{title=[WBWin]::Title($h); state=$state; window_state=$state; truncated=($tree.truncated -or $tree.items.Count -gt 120);
                 coordinate_system='client_physical_pixels'; client=@{width=$box[2];height=$box[3];screen_x=$box[0];screen_y=$box[1]}; controls=$rows}
    }
    if ($req.action -eq 'desktop_invoke') {
        if ((!!$req.element_id) -eq (!!$req.button_name)) {throw 'Specify either the exact button_name or one inspected element_id.'}
        if (![WBWin]::IsWindowEnabled($h)) {throw 'The selected window is disabled or modal.'}
        $tree=Get-WindowTree $h
        if (!$tree.page_known -or ($tree.truncated -and !$req.element_id)) {throw 'Cannot establish a unique button on this page; inspect and use element_id.'}
        $buttons=@(foreach ($el in $tree.items) {
            $cur=$el.Current
            if ($cur.ControlType -ne [System.Windows.Automation.ControlType]::Button -or !$cur.IsEnabled -or $cur.IsOffscreen) {continue}
            if ($req.binding.shell_surface -eq 'taskbar' -and $cur.ProcessId -ne $req.binding.process) {continue}
            if (($req.element_id -and (Get-ElementId $h $el $tree) -ceq $req.element_id) -or
                ($req.button_name -and (Test-Same $cur.Name $req.button_name))) {$el}
        })
        if ($buttons.Count -ne 1) {throw 'Expected one visible enabled button matching the requested target.'}
        $button=$buttons[0]
        $id=Get-ElementId $h $button $tree
        $invoke=$button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
        [void](Confirm-Target $req.binding)
        if (!$button.Current.IsEnabled -or $button.Current.IsOffscreen -or !$button.Current.IsControlElement -or
            ($req.button_name -and !(Test-Same $button.Current.Name $req.button_name))) {throw 'The selected button changed before invocation.'}
        if ($tree.browser) {
            $currentTree=Get-WindowTree $h
            if (!$currentTree.page_known -or !(Test-Same $currentTree.context $tree.context)) {throw 'The active browser document changed.'}
        }
        $buttonName=$button.Current.Name
        Start-DesktopEffect
        try {$invoke.Invoke(); $result=@{invoked=$buttonName; element_id=$id; status='completed'; detail='InvokePattern submitted.'}}
        catch {$result=@{element_id=$id; status='unknown'; detail='The button outcome is unknown. Inspect the window before continuing.'}}
        Set-DesktopReceipt $result
        return $result
    }
    if ($req.action -eq 'desktop_press_key') {
        $key=[string]$req.key
        if ($key -cnotin 'Ctrl+L','Enter') {throw 'Supported keys are Ctrl+L and Enter.'}
        $focus=Get-FocusedControl $h
        $proc=(Get-Process -Id $req.binding.process).ProcessName
        if ($key -ceq 'Ctrl+L' -and $proc -notin 'chrome','msedge','chromium','brave','vivaldi','opera') {throw 'Ctrl+L is only supported in a selected Chromium browser.'}
        if ($key -ceq 'Enter' -and $focus.Current.ControlType.ProgrammaticName -notin 'ControlType.Edit','ControlType.Button','ControlType.Hyperlink','ControlType.ComboBox','ControlType.Document') {
            throw 'The focused control does not support scoped Enter.'
        }
        [void](Confirm-Target $req.binding)
        if (![System.Windows.Automation.Automation]::Compare($focus,(Get-FocusedControl $h))) {throw 'Input focus changed before the shortcut.'}
        Start-DesktopEffect
        try {
            [WBWin]::Shortcut($h,$key)
            $result=@{key=$key;status='completed';delivered=$true;verified=$false;detail='Windows accepted the shortcut. Inspect the resulting focus or page.'}
        } catch {$result=@{key=$key;status='unknown';delivered=$null;verified=$false;detail='Inspect the resulting focus or page before continuing.'}}
        Set-DesktopReceipt $result
        return $result
    }
    if ($req.action -notin 'desktop_read_text','desktop_type_text') {throw 'Unknown action.'}
    if (($req.target -and $req.target -cne 'focused') -or ($req.target -and $req.element_id)) {throw 'Choose either element_id or target=focused.'}
    $editor=Get-Editor $h $req
    $value=[string](Read-Editor $editor)
    if ($req.action -eq 'desktop_read_text') {
        $editor=Confirm-Editor $h $req $editor
        $value=[string](Read-Editor $editor)
        return @{text=$value; source=$editor.source; element_id=$editor.id; title=[WBWin]::Title($h); verified=$true}
    }
    return Write-Editor $h $req $editor $value
}

try {
    $request=[Console]::In.ReadToEnd() | ConvertFrom-Json
    Assert-DesktopActive
    Initialize-Desktop
    [WBWin]::CancelPath=$request.cancel_path
    [WBWin]::ReceiptPath=$request.receipt_path
    Assert-DesktopActive
    if ($request.action -eq 'diagnostic') {$result=@{assemblies='ready'}} else {$result=Invoke-Desktop $request}
    [Console]::WriteLine((@{ok=$true; result=$result} | ConvertTo-Json -Compress -Depth 8))
} catch {
    [Console]::WriteLine((@{ok=$false; error=$_.Exception.Message} | ConvertTo-Json -Compress -Depth 4))
}
