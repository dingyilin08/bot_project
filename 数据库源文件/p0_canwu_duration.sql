-- 参悟时长持久化：旧的进行中参悟保留原 1200 秒，新参悟由程序写入 30~120 秒。
ALTER TABLE `user_zt`
  ADD COLUMN `cw_duration` int(11) NOT NULL DEFAULT 1200 COMMENT '本次参悟所需秒数'
  AFTER `cw_timestamp`;
