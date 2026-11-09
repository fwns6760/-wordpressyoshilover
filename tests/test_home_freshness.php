<?php
const HOUR_IN_SECONDS=3600;
class WP_Post {}
class WP_Query {
 public $posts=[];
 function __construct($args) {
  $GLOBALS['queries'][]=$args;
  if (empty($args['date_query'])) { throw new Exception('Undated recent query can revive stale posts'); }
 }
}
$GLOBALS['queries']=[];
$GLOBALS['cache']=false;
function get_transient($k){return $GLOBALS['cache'];}
function set_transient($k,$v,$ttl){$GLOBALS['cache']=$v;}
function current_time($fmt){return '2026-11-09';}
function wp_reset_postdata(){}
function yoshilover_063_breaking_strip_target_subtypes(){return [];}
function yoshilover_063_get_topic_hub_items(){throw new Exception('Today must not backfill weekly topics');}
$source=file_get_contents($argv[1] ?? (__DIR__.'/../src/yoshilover-063-frontend.php'));
foreach (['auto_topic_hub_items','get_breaking_strip_items','get_today_giants_box_items'] as $name) {
 if (!preg_match('/function yoshilover_063_'.$name.'\([^\n]*\).*?\n}\n/s',$source,$matches)) throw new Exception('Function missing');
 eval($matches[0]);
}
$old=[['title'=>'August article','url'=>'https://example.com/old']];
if (yoshilover_063_auto_topic_hub_items($old)!==[]) throw new Exception('Legacy fallback');
if (yoshilover_063_auto_topic_hub_items($old)!==[]) throw new Exception('Cached empty fallback');
if (yoshilover_063_get_today_giants_box_items()!==[]) throw new Exception('Stale today items');
if (count($GLOBALS['queries'])!==3) throw new Exception('Expected hot/recent/today queries');
echo "PASS: hot + recent bounded to week; today bounded; legacy/cache fallback removed\n";
