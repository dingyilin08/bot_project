-- 战斗 Buff 目标策略：1 表示施法者自身，2 表示施法目标。
-- 正向状态永远由施法者获得；本语义同时适用于玩家技能与 Boss 技能。
UPDATE data_skill
SET buff_target = 1
WHERE buff_duration > 0
  AND LOWER(TRIM(buff_type)) IN (
      'attack_up', 'gongji_up',
      'defense_up', 'fangyu_up',
      'speed_up', 'sudu_up',
      'crit_up', 'baoji_up', 'crit_dmg_up', 'baoshang_up',
      'dodge_up', 'shanbi_up', 'hit_up', 'mingzhong_up',
      'pierce_up', 'pofang_up', 'all_stat_up',
      'heal_over_time', 'hp_up', 'regeneration', 'lifesteal',
      'invincible', 'untargetable', 'shield', 'gedang', 'reflect',
      'defense_ignore', 'see_through', 'clone', 'resurrect',
      'immortal', 'god_mode', 'wudi', 'immune', 'transform'
  );

-- 负面状态、控制与持续伤害必须施加给施法目标。
UPDATE data_skill
SET buff_target = 2
WHERE buff_duration > 0
  AND LOWER(TRIM(buff_type)) IN (
      'attack_down', 'gongji_down',
      'defense_down', 'fangyu_down',
      'speed_down', 'sudu_down', 'slow', 'slow_down',
      'crit_down', 'baoji_down', 'dodge_down', 'shanbi_down',
      'hit_down', 'mingzhong_down', 'pierce_down', 'pofang_down',
      'damage_over_time', 'hp_down', 'burning', 'poison',
      'healing_down', 'stun', 'un_action', 'unaction_fy_down',
      'stun_defense_down', 'silence', 'disarm', 'confusion',
      'paralyze', 'blind', 'shackle', 'rooted', 'wet', 'suppress',
      'death_sentence', 'shock', 'mana_burn'
  );
