# First we explore the data
import code
import json
import pandas as pd
from sklearn.model_selection import train_test_split
from boruta import BorutaPy

import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, TensorDataset


def load_boruta_features():
    with open("./boruta_features/0ab8afba6aea0002289ca6fda41790a6de0cef02") as f:
        data = json.loads(f.read())
        return data["features"]


def drop_features_below_threshold(df, percent):
    """Drop a percentage of features based on value
    Eg: 0.7 will drop the bottom 70% of features,
    leaving the remaining 30%.

    Params:
        percent: float (0 - 1)


    Usage:
        df = drop_features_below_threshold(df, percent=0.8)
    """

    percent = min(percent, 1)

    # ignore labels
    feature_df = df.iloc[:, 1:]

    mean_values = feature_df.mean()

    # determine the number of columns to drop
    num_columns_to_drop = int(len(mean_values) * (percent / 100))

    # get the columns to drop based on the lowest mean values
    columns_to_drop = mean_values.nsmallest(num_columns_to_drop).index.tolist()

    df_trimmed = df.drop(columns=columns_to_drop)
    print(f"Dropped columns: {len(columns_to_drop)} out of {len(df.columns)}")

    return df_trimmed


def load_data(use_boruta_features_only: bool = False):
    """
    Load gene expression data and split into test/train
    Returns:
    """
    df = pd.read_csv("./G12/G12_breast_gene-expr.csv")

    # We drop the first column since it is just sample identifiers, not useful for machine learning
    df = df.drop(df.columns[0], axis=1)

    if use_boruta_features_only:
        # exclude any non boruta selected features!
        features = load_boruta_features()
        df = df[["Label"] + features]

    # Drop the label "Tumour" or "Normal Tissue" from the feature set.
    # The whole point is the features do **not** include the "answer"
    X = df.drop(df.columns[0], axis=1)

    print(f"Features: {df.shape[1]}")

    # y is the labels. This is **only** the Tumour or Normal Tissue labels.
    y = df["Label"]  # Labels

    # Convert labels to numeric values.
    y = y.map({"Primary Tumor": 1, "Solid Tissue Normal": 0})

    return X, y


def logistic_regression(X, y):
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    from sklearn.linear_model import LogisticRegression

    # new model instance
    # NOTE the actual "training" is when you run `fit()`
    model = LogisticRegression(max_iter=1000)

    # run the model
    # TODO: experiment with different iterations
    model.fit(X_train, y_train)

    # evaluate the model
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred)

    print(f"Accuracy: {accuracy:.2f}")
    print("Classification Report:")
    print(report)


def random_forest(X, y):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, classification_report

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)

    # Make predictions on the test set
    y_pred = model.predict(X_test)

    accuracy = accuracy_score(y_test, y_pred)
    print(f"Accuracy: {accuracy:.2f}")

    # Print classification report
    report = classification_report(y_test, y_pred)
    print("Classification Report:")
    print(report)
    return model


def run_boruta(estimator):
    boruta_selector = BorutaPy(
        estimator=estimator,
        n_estimators="auto",  # type: ignore based on estimator
        verbose=2,
        random_state=42,
    )

    boruta_selector.fit(X.values, y.values)
    selected_features = X.columns[boruta_selector.support_].to_list()

    print("Selected Features:")
    print(selected_features)


def forwardfeed_neural_net(X, y):
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # Standardize the features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Convert to PyTorch tensors
    X_train_tensor = torch.FloatTensor(X_train_scaled)
    y_train_tensor = torch.FloatTensor(y_train.values)
    X_test_tensor = torch.FloatTensor(X_test_scaled)
    y_test_tensor = torch.FloatTensor(y_test.values)

    # Create DataLoader
    train_dataset = TensorDataset(X_train_tensor, y_train_tensor)
    train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)

    # Define the neural network model
    class SimpleNN(nn.Module):
        def __init__(self, input_size):
            super(SimpleNN, self).__init__()
            self.fc1 = nn.Linear(input_size, 64)  # Input layer
            self.fc2 = nn.Linear(64, 32)  # Hidden layer
            self.fc3 = nn.Linear(32, 1)  # Output layer

        def forward(self, x):
            x = torch.relu(self.fc1(x))  # Activation for first layer
            x = torch.relu(self.fc2(x))  # Activation for second layer
            x = torch.sigmoid(self.fc3(x))  # Sigmoid for binary classification
            return x

    # Initialize the model
    input_size = X_train_scaled.shape[1]  # Number of features
    model = SimpleNN(input_size)

    # Define loss function and optimizer
    criterion = nn.BCELoss()  # Binary Cross-Entropy Loss
    optimizer = optim.Adam(model.parameters(), lr=0.001)

    # Train the model
    num_epochs = 100
    for epoch in range(num_epochs):
        for batch_X, batch_y in train_loader:
            optimizer.zero_grad()  # Clear gradients
            outputs = model(batch_X).squeeze()  # Forward pass
            loss = criterion(outputs, batch_y)  # Compute loss
            loss.backward()  # Backward pass
            optimizer.step()  # Update weights

        if (epoch + 1) % 10 == 0:
            print(f"Epoch [{epoch + 1}/{num_epochs}], Loss: {loss.item():.4f}")

    # Evaluate the model
    with torch.no_grad():
        model.eval()  # Set the model to evaluation mode
        y_test_pred = model(X_test_tensor).squeeze()
        y_test_pred_binary = (
            y_test_pred > 0.5
        ).float()  # Convert probabilities to binary predictions

    # Calculate accuracy
    accuracy = (y_test_pred_binary == y_test_tensor).float().mean()
    print(f"Test Accuracy: {accuracy:.2f}")

    y_test_numpy = y_test_tensor.numpy()
    y_test_pred_numpy = y_test_pred_binary.numpy()
    report = classification_report(
        y_test_numpy,
        y_test_pred_numpy,
        target_names=["Solid Tissue Normal", "Primary Tumor"],
    )
    print("Classification Report:")
    print(report)


# ==================================
# Run all the models

boruta_feats = load_boruta_features()

print(f"\n=== Logistic Regression (all features) ===\n")
X, y = load_data()
logistic_regression(X, y)

print(f"\n=== Logistic Regression (boruta features only = {len(boruta_feats)}) ===\n")
X, y = load_data(use_boruta_features_only=True)
logistic_regression(X, y)

print(f"\n=== Random Forest (all features) ===\n")
X, y = load_data()
random_forest(X, y)

print(f"\n=== Random Forest (boruta features only = {len(boruta_feats)}) ===\n")
X, y = load_data(use_boruta_features_only=True)
random_forest(X, y)

print(f"\n=== Fowrard Feed Neural Network (all features) ===\n")
X, y = load_data()
forwardfeed_neural_net(X, y)

print(
    f"\n=== Fowrard Feed Neural Network (boruta features only = {len(boruta_feats)}) ===\n"
)
X, y = load_data(use_boruta_features_only=True)
forwardfeed_neural_net(X, y)

# rf = random_forest()
# Warning: This takes a very long time. Let's preprocess
# run_boruta(rf)
