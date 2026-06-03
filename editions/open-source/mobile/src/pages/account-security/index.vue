<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import {
  changeMyPassword,
  disableMyTotp,
  enableMyTotp,
  fetchMySecurityProfile,
  setupMyTotp,
  type SecurityUserProfile,
  type TotpSetupResult
} from "@/api/security";

const loading = ref(false);
const savingTotp = ref(false);
const savingPassword = ref(false);
const profile = ref<SecurityUserProfile | null>(null);
const setupResult = ref<TotpSetupResult | null>(null);
const totpCode = ref("");
const loadMessage = ref("未刷新");
const loadAt = ref("");

const passwordForm = ref({
  current: "",
  next: "",
  confirm: ""
});

function setLoadStatus(message: string) {
  loadMessage.value = message;
  loadAt.value = new Date().toISOString();
}

const summaryText = computed(() => {
  const user = profile.value;
  return `账号安全：用户=${user?.username || "-"}；2FA=${user?.totp_enabled ? "已开启" : "未开启"}；角色=${user?.role || "-"}；状态=${user?.is_active === false ? "停用" : "正常"}`;
});

const nextStepAdvice = computed(() => {
  if (!profile.value?.totp_enabled) return "下一步建议：完成 2FA 绑定并开启验证码登录保护。";
  return "下一步建议：定期轮换密码并保管好验证器，避免单点风险。";
});

async function loadProfile() {
  loading.value = true;
  try {
    profile.value = await fetchMySecurityProfile();
    setLoadStatus("刷新成功");
  } catch (err: any) {
    profile.value = null;
    setLoadStatus(err?.message ? `刷新失败：${err.message}` : "刷新失败");
    uni.showToast({ title: "账号安全信息加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}

async function startSetup() {
  savingTotp.value = true;
  try {
    setupResult.value = await setupMyTotp();
    totpCode.value = "";
    uni.showToast({ title: "密钥已生成", icon: "none" });
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `生成失败：${err.message}` : "生成失败", icon: "none" });
  } finally {
    savingTotp.value = false;
  }
}

async function enableTotpNow() {
  const code = String(totpCode.value || "").trim();
  if (!code) {
    uni.showToast({ title: "请输入验证码", icon: "none" });
    return;
  }
  savingTotp.value = true;
  try {
    await enableMyTotp(code);
    setupResult.value = null;
    totpCode.value = "";
    uni.showToast({ title: "2FA 已开启", icon: "none" });
    await loadProfile();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `开启失败：${err.message}` : "开启失败", icon: "none" });
  } finally {
    savingTotp.value = false;
  }
}

async function disableTotpNow() {
  const code = String(totpCode.value || "").trim();
  if (!code) {
    uni.showToast({ title: "请输入验证码", icon: "none" });
    return;
  }
  savingTotp.value = true;
  try {
    await disableMyTotp(code);
    setupResult.value = null;
    totpCode.value = "";
    uni.showToast({ title: "2FA 已关闭", icon: "none" });
    await loadProfile();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `关闭失败：${err.message}` : "关闭失败", icon: "none" });
  } finally {
    savingTotp.value = false;
  }
}

function resetPasswordForm() {
  passwordForm.value = { current: "", next: "", confirm: "" };
}

async function submitPasswordChange() {
  const current = String(passwordForm.value.current || "");
  const next = String(passwordForm.value.next || "");
  const confirm = String(passwordForm.value.confirm || "");
  if (!current || !next || !confirm) {
    uni.showToast({ title: "请完整填写改密信息", icon: "none" });
    return;
  }
  if (next.length < 8) {
    uni.showToast({ title: "新密码至少 8 位", icon: "none" });
    return;
  }
  if (next !== confirm) {
    uni.showToast({ title: "两次新密码不一致", icon: "none" });
    return;
  }
  savingPassword.value = true;
  try {
    await changeMyPassword({
      current_password: current,
      new_password: next
    });
    uni.showToast({ title: "密码修改成功", icon: "none" });
    resetPasswordForm();
  } catch (err: any) {
    uni.showToast({ title: err?.message ? `改密失败：${err.message}` : "改密失败", icon: "none" });
  } finally {
    savingPassword.value = false;
  }
}

function copySummary() {
  const text = [summaryText.value, nextStepAdvice.value, `刷新状态：${loadMessage.value || "-"}`].join("；");
  uni.setClipboardData({
    data: text,
    success: () => uni.showToast({ title: "安全摘要已复制", icon: "none" }),
    fail: () => uni.showToast({ title: "复制失败，请重试", icon: "none" })
  });
}

onShow(loadProfile);
</script>

<template>
  <view class="app-page app-gap-12">
    <view class="app-title">账号安全</view>

    <view class="app-card app-gap-12">
      <view class="app-row">
        <text class="app-subtext">{{ summaryText }}</text>
        <button size="mini" :loading="loading" @click="loadProfile">刷新</button>
      </view>
      <text class="app-subtext">{{ nextStepAdvice }}</text>
      <text class="app-subtext">刷新状态：{{ loadMessage || "-" }}</text>
      <text class="app-subtext">状态时间：{{ loadAt || "-" }}</text>
      <view class="app-row">
        <button size="mini" @click="copySummary">复制摘要</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">两步验证（2FA / TOTP）</text>
      <text class="app-subtext">状态：{{ profile?.totp_enabled ? "已开启" : "未开启" }}</text>
      <text class="app-subtext">开启后登录需要额外输入 6 位动态验证码。</text>
      <view v-if="!profile?.totp_enabled" class="app-gap-12">
        <button size="mini" type="primary" :loading="savingTotp" @click="startSetup">生成密钥</button>
        <view v-if="setupResult" class="app-gap-12">
          <text class="app-subtext">密钥：{{ setupResult.secret }}</text>
          <textarea v-model="setupResult.otpauth_uri" class="app-textarea" />
          <input v-model="totpCode" placeholder="输入 6 位验证码以开启 2FA" />
          <button size="mini" type="primary" :loading="savingTotp" @click="enableTotpNow">确认开启</button>
        </view>
      </view>
      <view v-else class="app-gap-12">
        <input v-model="totpCode" placeholder="输入当前 6 位验证码以关闭 2FA" />
        <button size="mini" :loading="savingTotp" @click="disableTotpNow">关闭 2FA</button>
      </view>
    </view>

    <view class="app-card app-gap-12">
      <text class="app-subtext">修改密码</text>
      <input v-model="passwordForm.current" password placeholder="当前密码" />
      <input v-model="passwordForm.next" password placeholder="新密码（至少 8 位）" />
      <input v-model="passwordForm.confirm" password placeholder="确认新密码" />
      <view class="app-row">
        <button size="mini" type="primary" :loading="savingPassword" @click="submitPasswordChange">提交改密</button>
        <button size="mini" @click="resetPasswordForm">清空</button>
      </view>
    </view>
  </view>
</template>
