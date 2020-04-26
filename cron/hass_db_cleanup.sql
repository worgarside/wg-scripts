DELETE
FROM states
WHERE state = 'unknown'
   OR (
        state = '0' AND entity_id IN (
                                      'sensor.battery_will',
                                      'sensor.coinbase_bat_wallet_gbp_value',
                                      'sensor.coinbase_eos_wallet_gbp_value',
                                      'sensor.coinbase_xlm_wallet_gbp_value',
                                      'sensor.coinbase_dai_wallet_gbp_value',
                                      'sensor.coinbase_portfolio_value'
        )
    );