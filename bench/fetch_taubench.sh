#!/usr/bin/env bash
# Fetch the tau-bench historical trajectories (Sierra, MIT) into bench/data/taubench/.
# Real customer-service agent runs (retail and airline) with every tool result the agent saw.
# Pinned to one commit so the numbers reproduce.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p data/taubench
base=https://raw.githubusercontent.com/sierra-research/tau-bench/59a200c6d575d595120f1cb70fea53cef0632f6b/historical_trajectories
for f in gpt-4o-airline gpt-4o-retail sonnet-35-new-airline sonnet-35-new-retail; do
  [ -s "data/taubench/$f.json" ] || curl -fsSL "$base/$f.json" -o "data/taubench/$f.json"
done
# The tool definitions (JSON schemas) the agents were given: part of every prompt, not of the trajectories.
tools=https://raw.githubusercontent.com/sierra-research/tau-bench/59a200c6d575d595120f1cb70fea53cef0632f6b/tau_bench/envs
airline="book_reservation calculate cancel_reservation get_reservation_details get_user_details list_all_airports
  search_direct_flight search_onestop_flight send_certificate think transfer_to_human_agents
  update_reservation_baggages update_reservation_flights update_reservation_passengers"
retail="calculate cancel_pending_order exchange_delivered_order_items find_user_id_by_email find_user_id_by_name_zip
  get_order_details get_product_details get_user_details list_all_product_types modify_pending_order_address
  modify_pending_order_items modify_pending_order_payment modify_user_address return_delivered_order_items think
  transfer_to_human_agents"
for domain in airline retail; do
  mkdir -p "data/taubench/tools/$domain"
  names=$airline; [ "$domain" = retail ] && names=$retail
  for t in $names; do
    [ -s "data/taubench/tools/$domain/$t.py" ] || curl -fsSL "$tools/$domain/tools/$t.py" -o "data/taubench/tools/$domain/$t.py"
  done
done
echo "tau-bench trajectories and tool definitions ready in bench/data/taubench/"
