"""Verify persisted scores, targets, model reload and temporal leakage barriers."""
import json
import hashlib
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import average_precision_score
from tren_modell import ROOT,OUT,load,apply_cal,draw


def main():
    completion=json.loads((OUT/'completion.json').read_text(encoding='utf-8'))
    assert completion['complete']
    audit=json.loads((OUT/'data_audit.json').read_text(encoding='utf-8'))
    for source in audit['source_files']:
        assert hashlib.sha256((ROOT/source['file']).read_bytes()).hexdigest()==source['sha256']
    keys,y,x,weather,splits,sections=load(write_audit=False)
    # Check that lagging and moving windows cannot mix sections or use the target date.
    sample='46_EV134_S10'
    sample_date=pd.Timestamp('2025-02-10')
    yearly=pd.read_parquet(ROOT/'data/weather/strekning_dogn/2025.parquet',
                          filters=[('strekning_id','==',sample)]).set_index('dato')
    selected=(keys.strekning_id==sample)&(keys.dato==sample_date)
    feature=x.loc[selected].iloc[0]
    assert np.isclose(feature.nedbor_mm_lag1,yearly.loc[sample_date-pd.Timedelta(days=1),'nedbor_mm_mean'])
    days=pd.date_range(sample_date-pd.Timedelta(days=7),sample_date-pd.Timedelta(days=1))
    assert np.isclose(feature.nedbor_mm_sum7d_lag1,yearly.loc[days,'nedbor_mm_mean'].sum(),rtol=1e-5)
    assert np.isclose(feature.nedbor_mm_max_lag1,yearly.loc[sample_date-pd.Timedelta(days=1),'nedbor_mm_max'])
    checked=[]
    for scope in ['temporal','geographic']:
        folder=OUT/scope
        results=json.loads((folder/'metrics.json').read_text(encoding='utf-8'))
        for result in results:
            if result['split']!='test':
                continue
            name=result['model']
            p=pd.read_parquet(folder/f'{name}_test_predictions.parquet')
            assert not p.duplicated(['strekning_id','dato']).any()
            assert p.dato.min()==pd.Timestamp('2024-01-01') and p.dato.max()==pd.Timestamp('2026-10-03')
            assert p.score.between(0,1).all() and np.isfinite(p.score).all()
            index=pd.MultiIndex.from_frame(keys[['strekning_id','dato']])
            labels=pd.Series(y,index=index).reindex(pd.MultiIndex.from_frame(p[['strekning_id','dato']])).to_numpy()
            assert np.array_equal(labels,p.target)
            assert int(p.target.sum())==result['positives']
            # Float32 persistence slightly changes ties only below reporting precision.
            assert abs(average_precision_score(p.target,p.score)-result['average_precision'])<1e-5
            alerts=pd.read_csv(folder/f'{name}_test_top10.csv')
            assert (alerts.groupby('dato').size()==10).all()
            assert int(alerts.registered_event.sum())==result['true_positive_top10']
            assert len(alerts)-int(alerts.registered_event.sum())==result['false_alerts_top10']
            if name!='historical_frequency':
                meta=json.loads((folder/f'{name}_metadata.json').read_text(encoding='utf-8'))
                calibration=json.loads((folder/f'{name}_calibration.json').read_text(encoding='utf-8'))
                booster=lgb.Booster(model_file=str(folder/f'{name}.txt'))
                subset=p.sample(50,random_state=42)
                ix=index.get_indexer(pd.MultiIndex.from_frame(subset[['strekning_id','dato']]))
                assert np.all(ix>=0)
                raw=booster.predict(x.iloc[ix][meta['features']])
                assert np.allclose(raw,subset.raw_score,atol=1e-7,rtol=1e-6)
                assert np.allclose(apply_cal(raw,calibration),subset.score,atol=1e-7,rtol=1e-6)
            checked.append(f'{scope}/{name}')
        if scope=='geographic':
            geo=json.loads((folder/'geography.json').read_text())
            held=set(geo['held_section_ids'])
            train=set(geo['training_section_ids'])
            assert held.isdisjoint(train)
            assert set(p.strekning_id)==held
            coordinates=sections.set_index('strekning_id')
            assert coordinates.loc[list(held),'ymin'].min()-coordinates.loc[list(train),'ymax'].max()>4000
        # Re-render saved metrics only; this does not retrain or select on test results.
        draw(folder,results)
    selection=json.loads((OUT/'model_selection.json').read_text())
    validation=[m for m in completion['temporal'] if m['split']=='validation']
    assert selection['selected_on_validation']==max(validation,key=lambda m:m['recall_top10'])['model']
    result=dict(validated=True,checked=checked,
                checks=['source file hashes','lag and 7-day window alignment',
                        'test keys and labels','top-10 counts','metrics from saved predictions',
                        'reloaded model and calibration reproduce predictions','geographic separation',
                        'selection uses validation only'])
    (OUT/'validation_report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
