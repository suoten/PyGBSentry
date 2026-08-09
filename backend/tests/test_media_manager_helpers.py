"""测试 app/sip/ptz.py 中的 PTZ 指令生成函数（纯函数）。

media_manager.py 大部分是 async 方法依赖 DB/网络，不易单元测试；
改为测试 ptz.py 中接收参数返回十六进制字符串的纯函数：
  - _get_ptz_cmd：方向/缩放控制命令
  - _get_iris_cmd：光圈控制命令（in/out/stop）
  - _get_focus_cmd：聚焦控制命令（near/far/stop）
  - _get_preset_cmd / _get_preset_set_cmd / _get_preset_delete_cmd：预置位
  - _get_cruise_cmd：巡航控制
  - _get_scan_cmd：扫描控制
  - _get_wiper_cmd / _get_aux_switch_cmd：雨刷与辅助开关

GB28181 PTZ 命令格式（8 字节）：
  A5 0F 01 CmdCode Param1 Param2 CombineCode2 Checksum
其中 Checksum = (前 7 字节之和) mod 256
"""
import pytest

from app.sip.ptz import SipPtz


@pytest.fixture
def ptz() -> SipPtz:
    """SipPtz 的纯方法不依赖 sip_server，可传入 None 进行测试。"""
    return SipPtz(sip_server=None)


def _parse_hex(hex_str: str) -> list[int]:
    """将十六进制字符串解析为字节列表，便于断言。"""
    assert len(hex_str) % 2 == 0, f"十六进制字符串长度必须为偶数: {hex_str}"
    return [int(hex_str[i:i + 2], 16) for i in range(0, len(hex_str), 2)]


def _verify_checksum(hex_str: str) -> int:
    """验证 GB28181 PTZ 命令的校验和（前 7 字节之和 mod 256 = 第 8 字节）。"""
    bytes_list = _parse_hex(hex_str)
    assert len(bytes_list) == 8, f"PTZ 命令必须为 8 字节，实际: {len(bytes_list)}"
    expected = sum(bytes_list[:7]) % 256
    actual = bytes_list[7]
    assert expected == actual, \
        f"校验和不匹配：前7字节和={expected} (0x{expected:02X})，实际 checksum={actual} (0x{actual:02X})"
    return actual


# ---------------------------------------------------------------------------
# 1. _get_ptz_cmd 方向控制
# ---------------------------------------------------------------------------

class TestGetPtzCmd:
    """验证 _get_ptz_cmd 生成方向/缩放控制命令。"""

    def test_right_command(self, ptz):
        """right 方向：CmdCode=0x01，Param1=speed。"""
        result = ptz._get_ptz_cmd(cmd_code=0x01, param1=50, parameter2=0, combine_code2=0)
        assert len(result) == 16, "8字节 = 16 个十六进制字符"
        bytes_list = _parse_hex(result)
        # 验证头部 A5 0F 01
        assert bytes_list[:3] == [0xA5, 0x0F, 0x01]
        # 验证 CmdCode 与 Param1
        assert bytes_list[3] == 0x01
        assert bytes_list[4] == 50
        # 验证校验和
        _verify_checksum(result)

    def test_left_command(self, ptz):
        """left 方向：CmdCode=0x02。"""
        result = ptz._get_ptz_cmd(cmd_code=0x02, param1=50, parameter2=0, combine_code2=0)
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x02
        _verify_checksum(result)

    def test_down_command(self, ptz):
        """down 方向：CmdCode=0x04，Param2=speed。"""
        result = ptz._get_ptz_cmd(cmd_code=0x04, param1=0, parameter2=50, combine_code2=0)
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x04
        assert bytes_list[5] == 50  # Param2 (parameter2)
        _verify_checksum(result)

    def test_up_command(self, ptz):
        """up 方向：CmdCode=0x08。"""
        result = ptz._get_ptz_cmd(cmd_code=0x08, param1=0, parameter2=50, combine_code2=0)
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x08
        _verify_checksum(result)

    def test_zoomin_command(self, ptz):
        """zoomin：CmdCode=0x10。"""
        result = ptz._get_ptz_cmd(cmd_code=0x10, param1=0, parameter2=0, combine_code2=0x50)
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x10
        _verify_checksum(result)

    def test_zoomout_command(self, ptz):
        """zoomout：CmdCode=0x20。"""
        result = ptz._get_ptz_cmd(cmd_code=0x20, param1=0, parameter2=0, combine_code2=0x50)
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x20
        _verify_checksum(result)

    def test_stop_command(self, ptz):
        """stop：所有字段为 0。"""
        result = ptz._get_ptz_cmd(cmd_code=0x00, param1=0, parameter2=0, combine_code2=0)
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x00
        _verify_checksum(result)
        # 验证完整字符串：A5 0F 01 00 00 00 00 + 校验和
        # (0xA5 + 0x0F + 0x01) = 0xB5 = 181，181 mod 256 = 181 = 0xB5
        assert result == "A50F0100000000B5", f"stop 完整字符串不匹配: {result}"

    def test_combine_code2_masked_to_high_nibble(self, ptz):
        """combine_code2 应被 & 0xF0 屏蔽低 4 位。"""
        # 传入 0x55，应被屏蔽为 0x50
        result = ptz._get_ptz_cmd(cmd_code=0x00, param1=0, parameter2=0, combine_code2=0x55)
        bytes_list = _parse_hex(result)
        assert bytes_list[6] == 0x50, "combine_code2 低 4 位必须被屏蔽为 0"

    def test_output_is_uppercase_hex(self, ptz):
        """输出应为大写十六进制字符串。"""
        result = ptz._get_ptz_cmd(cmd_code=0xAB, param1=0, parameter2=0, combine_code2=0)
        # 全部字符必须在 0-9A-F 范围
        assert all(c in "0123456789ABCDEF" for c in result), \
            f"输出必须为大写十六进制: {result}"


# ---------------------------------------------------------------------------
# 2. _get_iris_cmd 光圈控制
# ---------------------------------------------------------------------------

class TestGetIrisCmd:
    """验证 _get_iris_cmd 生成光圈控制命令（CombineCode2 高 4 位）。"""

    def test_iris_in_sets_combine_code2_0x10(self, ptz):
        """iris in（光圈增大）：CombineCode2 高 4 位 = 0x10。"""
        result = ptz._get_iris_cmd("in")
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x00, "iris 命令 CmdCode 必须为 0x00"
        assert bytes_list[6] == 0x10, "iris in 必须设置 CombineCode2 高 4 位为 0x10"
        _verify_checksum(result)

    def test_iris_out_sets_combine_code2_0x20(self, ptz):
        """iris out（光圈减小）：CombineCode2 高 4 位 = 0x20。"""
        result = ptz._get_iris_cmd("out")
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x00
        assert bytes_list[6] == 0x20, "iris out 必须设置 CombineCode2 高 4 位为 0x20"
        _verify_checksum(result)

    def test_iris_stop_zero_combine_code2(self, ptz):
        """iris stop：CombineCode2 = 0x00。"""
        result = ptz._get_iris_cmd("stop")
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x00
        assert bytes_list[6] == 0x00
        _verify_checksum(result)

    def test_iris_in_full_string(self, ptz):
        """iris in 完整字符串应为 A50F0100000010C5。"""
        result = ptz._get_iris_cmd("in")
        # 手工计算：0xA5+0x0F+0x01+0x00+0x00+0x00+0x10 = 0xC5
        assert result == "A50F0100000010C5", f"iris in 完整字符串不匹配: {result}"

    def test_iris_out_full_string(self, ptz):
        """iris out 完整字符串应为 A50F0100000020D5。"""
        result = ptz._get_iris_cmd("out")
        # 手工计算：0xA5+0x0F+0x01+0x00+0x00+0x00+0x20 = 0xD5
        assert result == "A50F0100000020D5", f"iris out 完整字符串不匹配: {result}"


# ---------------------------------------------------------------------------
# 3. _get_focus_cmd 聚焦控制
# ---------------------------------------------------------------------------

class TestGetFocusCmd:
    """验证 _get_focus_cmd 生成聚焦控制命令（CmdCode 高 2 位）。"""

    def test_focus_near_sets_cmd_code_0x80(self, ptz):
        """focus near（近焦）：CmdCode bit7 = 0x80。"""
        result = ptz._get_focus_cmd("near")
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x80, "focus near 必须设置 CmdCode bit7 (0x80)"
        assert bytes_list[6] == 0x00, "focus 命令 CombineCode2 必须为 0"
        _verify_checksum(result)

    def test_focus_far_sets_cmd_code_0x40(self, ptz):
        """focus far（远焦）：CmdCode bit6 = 0x40。"""
        result = ptz._get_focus_cmd("far")
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x40, "focus far 必须设置 CmdCode bit6 (0x40)"
        _verify_checksum(result)

    def test_focus_stop_zero_cmd_code(self, ptz):
        """focus stop：CmdCode = 0x00。"""
        result = ptz._get_focus_cmd("stop")
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x00
        _verify_checksum(result)

    def test_focus_near_full_string(self, ptz):
        """focus near 完整字符串应为 A50F018000000035（校验和 0x35）。"""
        result = ptz._get_focus_cmd("near")
        # 手工计算：0xA5+0x0F+0x01+0x80 = 0x135；0x135 mod 256 = 0x35
        assert result == "A50F018000000035", f"focus near 完整字符串不匹配: {result}"

    def test_focus_far_full_string(self, ptz):
        """focus far 完整字符串应为 A50F0140000000F5（校验和 0xF5）。"""
        result = ptz._get_focus_cmd("far")
        # 手工计算：0xA5+0x0F+0x01+0x40 = 0xF5
        assert result == "A50F0140000000F5", f"focus far 完整字符串不匹配: {result}"


# ---------------------------------------------------------------------------
# 4. _get_preset_* 预置位控制
# ---------------------------------------------------------------------------

class TestGetPresetCmd:
    """验证预置位相关命令。"""

    def test_preset_goto_cmd(self, ptz):
        """预置位调用：CmdCode=0x82，preset_id 在 Param2 位置。"""
        result = ptz._get_preset_cmd(5)
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x82
        assert bytes_list[5] == 5, "preset_id 应在 Param2 位置"
        _verify_checksum(result)

    def test_preset_set_cmd(self, ptz):
        """预置位设置：CmdCode=0x81。"""
        result = ptz._get_preset_set_cmd(10)
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x81
        assert bytes_list[5] == 10
        _verify_checksum(result)

    def test_preset_delete_cmd(self, ptz):
        """预置位删除：CmdCode=0x83。"""
        result = ptz._get_preset_delete_cmd(15)
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x83
        assert bytes_list[5] == 15
        _verify_checksum(result)

    def test_preset_id_clamped_to_min(self, ptz):
        """preset_id < 1 应被 clamp 到 1。"""
        result = ptz._get_preset_cmd(0)
        bytes_list = _parse_hex(result)
        assert bytes_list[5] == 1, "preset_id 应被 clamp 到最小值 1"

    def test_preset_id_clamped_to_max(self, ptz):
        """preset_id > 255 应被 clamp 到 255。"""
        result = ptz._get_preset_cmd(999)
        bytes_list = _parse_hex(result)
        assert bytes_list[5] == 255, "preset_id 应被 clamp 到最大值 255"


# ---------------------------------------------------------------------------
# 5. _get_cruise_cmd 巡航控制
# ---------------------------------------------------------------------------

class TestGetCruiseCmd:
    """验证巡航控制命令。"""

    def test_cruise_add(self, ptz):
        """巡航添加预置位：CmdCode=0x82。"""
        result = ptz._get_cruise_cmd(cruise_id=1, preset_id=5, action="add")
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x82
        assert bytes_list[4] == 1  # cruise_id
        assert bytes_list[5] == 5  # preset_id
        _verify_checksum(result)

    def test_cruise_delete(self, ptz):
        """巡航删除预置位：CmdCode=0x83。"""
        result = ptz._get_cruise_cmd(cruise_id=2, preset_id=3, action="delete")
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x83

    def test_cruise_start(self, ptz):
        """开始巡航：CmdCode=0x86。"""
        result = ptz._get_cruise_cmd(cruise_id=1, preset_id=1, action="start")
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x86
        assert bytes_list[4] == 1
        _verify_checksum(result)

    def test_cruise_stop(self, ptz):
        """停止巡航：CmdCode=0x87。"""
        result = ptz._get_cruise_cmd(cruise_id=1, preset_id=1, action="stop")
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x87

    def test_cruise_set_speed(self, ptz):
        """设置巡航速度：CmdCode=0x84，speed 拆为高/低字节。"""
        result = ptz._get_cruise_cmd(cruise_id=1, preset_id=1, action="set_speed", speed=300)
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x84
        # speed=300 = 0x012C，高字节=0x01，低字节=0x2C
        assert bytes_list[5] == 0x01
        assert bytes_list[6] == 0x2C
        _verify_checksum(result)

    def test_cruise_set_time(self, ptz):
        """设置停留时间：CmdCode=0x85。"""
        result = ptz._get_cruise_cmd(cruise_id=1, preset_id=1, action="set_time", stay_time=10)
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x85
        # stay_time=10 = 0x000A，高字节=0x00，低字节=0x0A
        assert bytes_list[5] == 0x00
        assert bytes_list[6] == 0x0A
        _verify_checksum(result)


# ---------------------------------------------------------------------------
# 6. _get_scan_cmd 扫描控制
# ---------------------------------------------------------------------------

class TestGetScanCmd:
    """验证扫描控制命令。"""

    def test_scan_start(self, ptz):
        """扫描开始：CmdCode=0x99。"""
        result = ptz._get_scan_cmd(scan_id=1, action="start")
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x99
        assert bytes_list[4] == 1
        _verify_checksum(result)

    def test_scan_stop(self, ptz):
        """扫描停止：CmdCode=0x9A。"""
        result = ptz._get_scan_cmd(scan_id=1, action="stop")
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x9A

    def test_scan_set_left(self, ptz):
        """设置左边界：CmdCode=0x9B。"""
        result = ptz._get_scan_cmd(scan_id=2, action="set_left")
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x9B

    def test_scan_set_right(self, ptz):
        """设置右边界：CmdCode=0x9C。"""
        result = ptz._get_scan_cmd(scan_id=2, action="set_right")
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x9C

    def test_scan_set_speed(self, ptz):
        """设置扫描速度：CmdCode=0x9D。"""
        result = ptz._get_scan_cmd(scan_id=1, action="set_speed", speed=100)
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x9D
        # speed=100 = 0x0064
        assert bytes_list[5] == 0x00
        assert bytes_list[6] == 0x64
        _verify_checksum(result)

    def test_scan_id_clamped_to_min(self, ptz):
        """scan_id < 0 应被 clamp 到 0。"""
        result = ptz._get_scan_cmd(scan_id=-5, action="start")
        bytes_list = _parse_hex(result)
        assert bytes_list[4] == 0


# ---------------------------------------------------------------------------
# 7. _get_wiper_cmd / _get_aux_switch_cmd 设备控制
# ---------------------------------------------------------------------------

class TestGetWiperCmd:
    """验证雨刷控制命令。"""

    def test_wiper_on(self, ptz):
        """雨刷开：Param2=0x01。"""
        result = ptz._get_wiper_cmd("on")
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x30
        assert bytes_list[5] == 0x01
        _verify_checksum(result)

    def test_wiper_off(self, ptz):
        """雨刷关：Param2=0x00。"""
        result = ptz._get_wiper_cmd("off")
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x30
        assert bytes_list[5] == 0x00
        _verify_checksum(result)


class TestGetAuxSwitchCmd:
    """验证辅助开关命令。"""

    def test_aux_on(self, ptz):
        """辅助开：state=0x01。"""
        result = ptz._get_aux_switch_cmd(aux_id=2, command="on")
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x31
        assert bytes_list[4] == 2
        assert bytes_list[5] == 0x01
        _verify_checksum(result)

    def test_aux_off(self, ptz):
        """辅助关：state=0x00。"""
        result = ptz._get_aux_switch_cmd(aux_id=3, command="off")
        bytes_list = _parse_hex(result)
        assert bytes_list[3] == 0x31
        assert bytes_list[4] == 3
        assert bytes_list[5] == 0x00
        _verify_checksum(result)

    def test_aux_id_clamped_to_min(self, ptz):
        """aux_id < 2 应被 clamp 到 2。"""
        result = ptz._get_aux_switch_cmd(aux_id=1, command="on")
        bytes_list = _parse_hex(result)
        assert bytes_list[4] == 2

    def test_aux_id_clamped_to_max(self, ptz):
        """aux_id > 255 应被 clamp 到 255。"""
        result = ptz._get_aux_switch_cmd(aux_id=999, command="on")
        bytes_list = _parse_hex(result)
        assert bytes_list[4] == 255


# ---------------------------------------------------------------------------
# 8. 通用格式验证
# ---------------------------------------------------------------------------

class TestPtzCommandFormat:
    """验证所有 PTZ 命令的格式合规性。"""

    @pytest.mark.parametrize("command,kwargs", [
        ("_get_ptz_cmd", {"cmd_code": 0x01, "param1": 50, "parameter2": 0, "combine_code2": 0}),
        ("_get_iris_cmd", {"command": "in"}),
        ("_get_iris_cmd", {"command": "out"}),
        ("_get_iris_cmd", {"command": "stop"}),
        ("_get_focus_cmd", {"command": "near"}),
        ("_get_focus_cmd", {"command": "far"}),
        ("_get_focus_cmd", {"command": "stop"}),
        ("_get_preset_cmd", {"preset_id": 5}),
        ("_get_preset_set_cmd", {"preset_id": 5}),
        ("_get_preset_delete_cmd", {"preset_id": 5}),
        ("_get_cruise_cmd", {"cruise_id": 1, "preset_id": 1, "action": "start"}),
        ("_get_scan_cmd", {"scan_id": 1, "action": "start"}),
        ("_get_wiper_cmd", {"command": "on"}),
        ("_get_aux_switch_cmd", {"aux_id": 2, "command": "on"}),
    ])
    def test_command_is_16_hex_chars(self, ptz, command, kwargs):
        """所有 PTZ 命令必须是 16 个十六进制字符（8 字节）。"""
        method = getattr(ptz, command)
        result = method(**kwargs)
        assert len(result) == 16, \
            f"{command}({kwargs}) 输出长度必须为 16，实际: {len(result)} ({result})"
        # 全部字符必须在 0-9A-F 范围
        assert all(c in "0123456789ABCDEF" for c in result), \
            f"{command}({kwargs}) 输出必须为大写十六进制: {result}"
        # 校验和必须正确
        _verify_checksum(result)

    def test_all_commands_start_with_a5_0f_01(self, ptz):
        """所有 PTZ 命令的前 3 字节必须是 A5 0F 01（GB28181 PTZ 头部）。"""
        commands = [
            ptz._get_ptz_cmd(0x00, 0, 0, 0),
            ptz._get_iris_cmd("in"),
            ptz._get_focus_cmd("near"),
            ptz._get_preset_cmd(1),
            ptz._get_cruise_cmd(1, 1, "start"),
            ptz._get_scan_cmd(1, "start"),
            ptz._get_wiper_cmd("on"),
            ptz._get_aux_switch_cmd(2, "on"),
        ]
        for cmd in commands:
            assert cmd.startswith("A50F01"), \
                f"PTZ 命令必须以 'A50F01' 开头: {cmd}"
