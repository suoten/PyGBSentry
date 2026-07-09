<script setup lang="ts">
import { onLaunch, onError, onUnhandledRejection } from "@dcloudio/uni-app";

onLaunch(() => {
  console.log("[App] launched");
});

onError((err) => {
  console.error("[App Error]", err);
});

onUnhandledRejection((err) => {
  console.error("[App Unhandled Rejection]", err);
});
</script>

<style lang="scss">
@import "./uni.scss";
</style>
