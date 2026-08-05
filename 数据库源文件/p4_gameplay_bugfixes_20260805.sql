-- 2026-08-05：播种/战斗一致性修复配套数据。
-- 正向 Buff 固定作用于施法者，避免历史错误 target 值把增益加给怪物。
UPDATE data_skill
SET buff_target = 1
WHERE buff_duration > 0
  AND LOWER(TRIM(buff_type)) IN (
      'attack_up', 'gongji_up', 'defense_up', 'fangyu_up',
      'speed_up', 'sudu_up', 'crit_up', 'baoji_up',
      'crit_dmg_up', 'baoshang_up', 'dodge_up', 'shanbi_up',
      'hit_up', 'mingzhong_up', 'pierce_up', 'pofang_up',
      'all_stat_up', 'heal', 'heal_over_time', 'hp_up', 'regeneration',
      'lifesteal', 'invincible', 'untargetable', 'shield', 'gedang',
      'reflect', 'defense_ignore', 'see_through', 'clone', 'resurrect',
      'immortal', 'god_mode', 'wudi', 'immune', 'transform'
  );

-- 至尊骨按角色增益技能修正：治疗后强化自身，而不是给敌方挂无效压制状态。
UPDATE data_skill
SET buff_type = 'all_stat_up',
    buff_target = 1,
    buff_desc = '自身全属性提升25%，持续3回合'
WHERE role_name = '石昊'
  AND skill_name = '至尊骨';

-- 扫荡副本券每日限购提升至20张。
UPDATE data_shop_item
SET daily_limit = 20
WHERE item_id = 211;
