using System;
using System.IO;
using System.Windows.Forms;
using System.Drawing;
using Accessibility;

public static partial class WBWin {
    static readonly IntPtr Desktop = new IntPtr(1), View = new IntPtr(2), List = new IntPtr(3);
    static readonly IntPtr Prior = new IntPtr(4), Other = new IntPtr(5);
    static IntPtr Front = Prior, Receiver = List;
    static string Case;
    static Point Cursor = new Point {x=11, y=11};
    static int Sent, ForegroundChecks;

    // Managed accessibility objects with no HWND, COM provider, or shell calls.
    sealed class Icon : AccessibleObject {
        public override string Name {get{return Case=="item_between" && Sent==1 ? "Other shortcut" : "Test shortcut";}}
        public override AccessibleRole Role {get{return AccessibleRole.ListItem;}}
        public override Rectangle Bounds {get{return new Rectangle(10,10,50,55);}}
        public override AccessibleStates State {get{return AccessibleStates.Selectable;}}
    }
    sealed class IconList : AccessibleObject {
        public override AccessibleObject GetChild(int index) {return index==0 ? FakeIcon : null;}
        public override int GetChildCount() {return 1;}
        public override string Name {get{return "Desktop list";}}
        public override AccessibleRole Role {get{return AccessibleRole.List;}}
    }
    static readonly Icon FakeIcon=new Icon();
    static readonly IAccessible FakeList=new IconList();

    static IntPtr FakeForeground() {
        if (Case=="regain_prior" && Sent==1 && ++ForegroundChecks>=4) return Prior;
        return Front;
    }

    static string FakeClass(IntPtr h) {
        if (h == Desktop) return "Progman";
        if (h == View) return "SHELLDLL_DefView";
        if (h == List) return "SysListView32";
        return "SomeOtherApp";
    }

    static uint FakeSend(uint n, Input[] inputs) {
        if (n!=2 || inputs.Length!=2 || inputs[0].mouse.flags!=2 || inputs[1].mouse.flags!=4)
            throw new InvalidOperationException("Unexpected input sequence");
        Sent++;
        if (Sent==1) {
            if (Case=="changed_receiver") Receiver=Other;
            if (Case=="move_between") Cursor.x++;
            if (Case=="focus_between") Front=Other;
            if (Case=="activate_between" || Case=="regain_prior") Front=Desktop;
        }
        return 2;
    }

    public static int Main(string[] args) {
        Case=args[0]; ReceiptPath=args[1];
        if (Case=="occluded") Receiver=Other;
        if (Case=="unknown_foreground") Front=IntPtr.Zero;
        IntPtr target=Case=="ordinary" ? Other : Desktop;
        int expected=1;
        if (Case=="visible" || Case=="item_self" || Case=="activate_between") expected=2;
        if (Case=="occluded" || Case=="ordinary" || Case=="blank" || Case=="unknown_foreground") expected=0;
        string observed="";
        try {
            PreparePointer(target,20,20,2, Case=="ordinary" ? "" : "desktop",7,"");
            PointerResult result=Pointer(target,20,20,2,7,"");
            if (result.completed!=Sent || result.partial!=(Sent==1))
                throw new InvalidOperationException("Result disagrees with independently observed mouse events");
            observed=result.detail;
        } catch(Exception e) {
            if (expected!=0 || e is NotSupportedException || e is InvalidOperationException) {
                Console.Error.WriteLine(Case+": "+e); return 1;
            }
            observed=e.Message;
        } finally {EndInputGuard();}
        string receipt=File.ReadAllText(ReceiptPath);
        if (Sent!=expected || !receipt.Contains("\"completed_clicks\":"+expected+",") ||
            (expected==0 && !receipt.Contains("\"status\":\"failed\"")) ||
            (expected==1 && !receipt.Contains("\"status\":\"partial\"")) ||
            (expected==2 && (!receipt.Contains("\"status\":\"completed\"") || !DesktopIconVerified || ActivationMethod!="exposed_desktop_icon"))) {
            Console.Error.WriteLine(Case+" sent="+Sent+", receipt="+receipt+", detail="+observed); return 1;
        }
        Console.WriteLine(Case+": "+Sent+" completed pairs, "+observed); return 0;
    }
}
