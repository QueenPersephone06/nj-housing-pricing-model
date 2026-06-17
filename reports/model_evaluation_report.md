# Model Evaluation Report

_Hedonic pricing — Linear & Ridge regression on NJ active listings_

- Train set: **4,809** rows
- Test set:  **1,203** rows
- Features:  numerical = ['bedrooms', 'bathrooms', 'sqft', 'lot_size', 'year_built'] · categorical = ['county', 'municipality', 'property_type']

## Linear Regression

- Test MAE:  $105,989
- Test RMSE: $226,508
- Test R²:   0.4735
- 5-fold CV R² (mean ± std): 0.4197 ± 0.2121
- 5-fold CV MAE: $108,934

## Ridge Regression

- Best α (grid search): **100.0**
- Test MAE:  $100,739
- Test RMSE: $220,999
- Test R²:   0.4988
- 5-fold CV R²: 0.4088

Coefficients (top by absolute value) are persisted in `outputs/models/{linreg,ridge}_coefficients.csv`.
Both pipelines are serialized to joblib for direct reuse: `outputs/models/linreg.joblib` and `outputs/models/ridge.joblib`.