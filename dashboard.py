import streamlit as st
import pandas as pd
import numpy as np
import statsmodels.api as sm
import altair as alt

# ---------------------------------------------------------------------
# Page Configuration
# ---------------------------------------------------------------------
# Use the full screen width
st.set_page_config(layout="wide")

# ---------------------------------------------------------------------
# Data Loading (with Caching)
# ---------------------------------------------------------------------

@st.cache_data
def load_vax_cleaned_data():
    """Loads the cleaned vaccinations dataset for the EDA page."""
    try:
        df = pd.read_csv("vaccinations_cleaned.csv", parse_dates=['date'])
        return df
    except FileNotFoundError:
        st.error("Error: `vaccinations_cleaned.csv` not found. Please place it in the same directory.")
        return None

@st.cache_data
def load_analysis_data():
    """
    Performs the full data preparation pipeline for the Vax vs. Deaths analysis.
    This function contains all the cleaning, merging, and normalization logic.
    """
    try:
        ## --- 1. Load WHO Excess Deaths Data ---
        # The file is a true .xlsx file, so we use pd.read_excel.
        # This requires the 'openpyxl' library to be installed.
        deaths_file = "WHO_COVID_Excess_Deaths_Estimates_By_Countries.xlsx"
                
        # Use pd.read_excel, which correctly handles .xlsx files.
        # The outer try/except block in your function will catch any errors.
        deaths_df = pd.read_excel(deaths_file, skiprows=10)
        
        deaths_df.rename(columns={'excess.mean*': 'excess_deaths'}, inplace=True)
        deaths_agg = deaths_df.groupby(['iso3', 'country', 'year'])['excess_deaths'].sum().reset_index()
        deaths_2021 = deaths_agg[deaths_agg['year'] == 2021].copy()

        # --- 2. Load and Clean ORIGINAL Vaccination Data ---
        # We must use the original file to get correct daily_vaccinations for population
        vax_df = pd.read_csv("vaccinations.csv")
        vax_df['date'] = pd.to_datetime(vax_df['date'])
        vax_columns = [
            'people_fully_vaccinated_per_hundred', 'total_boosters_per_hundred',
            'daily_vaccinations_per_million', 'daily_vaccinations'
        ]
        vax_df = vax_df.sort_values(by=['iso_code', 'date'])
        
        # Apply forward-fill logic
        vax_df[vax_columns] = vax_df.groupby('iso_code')[vax_columns].ffill()
        vax_df[vax_columns] = vax_df[vax_columns].fillna(0)
        
        vax_2021_full = vax_df[vax_df['date'].dt.year == 2021].copy()
        vax_2021_eoy = vax_2021_full.loc[vax_2021_full.groupby('iso_code')['date'].idxmax()].copy()

        # --- 3. Derive Population ---
        vax_2021_eoy['population'] = np.where(
            vax_2021_eoy['daily_vaccinations_per_million'] > 0,
            (vax_2021_eoy['daily_vaccinations'] / vax_2021_eoy['daily_vaccinations_per_million']) * 1_000_000,
            0
        )
        vax_final_columns = [
            'iso_code', 'people_fully_vaccinated_per_hundred', 'total_boosters_per_hundred',
            'daily_vaccinations_per_million', 'population'
        ]
        vax_2021 = vax_2021_eoy[vax_final_columns]

        # --- 4. Merge and Normalize ---
        merged_df = pd.merge(deaths_2021, vax_2021, left_on='iso3', right_on='iso_code', how='inner')
        merged_df['excess_deaths_per_million'] = np.where(
            merged_df['population'] > 0,
            (merged_df['excess_deaths'] / merged_df['population']) * 1_000_000,
            0
        )
        final_df = merged_df[(merged_df['population'] > 10000) & (merged_df['excess_deaths'] != 0)].copy()
        
        return final_df
    
    except FileNotFoundError as e:
        st.error(f"Error: A required file was not found: {e.filename}. Make sure 'vaccinations.csv' and 'WHO_COVID_Excess_Deaths_Estimates_By_Countries.xlsx' are in the same directory.")
        return None
    except Exception as e:
        st.error(f"An unexpected error occurred during data loading: {e}")
        return None

# ---------------------------------------------------------------------
# Page Functions
# ---------------------------------------------------------------------

def page_intro():
    st.title("Global COVID-19 Vaccination Analysis 💉")
    st.markdown("""
    This dashboard provides a comprehensive overview of the analyses performed on the COVID-19 vaccination and WHO excess deaths datasets. 
    Use the navigation panel on the left to explore each project and its findings.
    """)

    st.header("Our Datasets")
    st.subheader("1. Vaccinations Dataset")
    st.markdown("""
    - **Content:** Detailed daily vaccination data for countries worldwide, including total vaccinations, people vaccinated, boosters, and per-capita metrics.
    - Dataset Source: https://www.nature.com/articles/s41562-021-01122-8 
    - Rows: 196246
    - Columns: 16

    #### Dataset Description

    Country-by-country data on global COVID-19 vaccinations. We only rely on figures that are verifiable based on public official sources.

    This dataset includes some subnational locations (England, Northern Ireland, Scotland, Wales, Northern Cyprus…) and international aggregates (World, continents, European Union…). They can be identified by their iso_code that starts with OWID_.

    #### Columns Description
    | Column Name | Description |
    | :------- | :------- |
    | `location` | Name of the country (or region within a country) |
    | `iso_code` | ISO 3166-1 alpha-3 - three-letter country codes |
    | `date` | Date of the observation |
    | `total_vaccinations` | Total number of doses administered. For vaccines that require multiple doses, each individual dose is counted. If a person receives one dose of the vaccine, this metric goes up by 1. If they receive a second dose, it goes up by 1 again. If they receive a third/booster dose, it goes up by 1 again |
    | `people_vaccinated` | Total number of people who received at least one vaccine dose. If a person receives the first dose of a 2-dose vaccine, this metric goes up by 1. If they receive the second dose, the metric stays the same |
    | `people_fully_vaccinated` | Total number of people who received all doses prescribed by the initial vaccination protocol. If a person receives the first dose of a 2-dose vaccine, this metric stays the same. If they receive the second dose, the metric goes up by 1 |
    | `total_boosters` | Total number of COVID-19 vaccination booster doses administered (doses administered beyond the number prescribed by the initial vaccination protocol) |
    | `daily_vaccinations_raw` | Daily change in the total number of doses administered. It is only calculated for consecutive days. This is a raw measure provided for data checks and transparency, but we strongly recommend that any analysis on daily vaccination rates be conducted using daily_vaccinations instead |
    | `daily_vaccinations` | New doses administered per day (7-day smoothed). For countries that don't report data on a daily basis, we assume that doses changed equally on a daily basis over any periods in which no data was reported. This produces a complete series of daily figures, which is then averaged over a rolling 7-day window |
    | `total_vaccinations_per_hundred` | total_vaccinations per 100 people in the total population of the country |
    | `people_vaccinated_per_hundred` | people_vaccinated per 100 people in the total population of the country |
    | `people_fully_vaccinated_per_hundred` | people_fully_vaccinated per 100 people in the total population of the country |
    | `total_boosters_per_hundred` | total_boosters per 100 people in the total population of the country |
    | `daily_vaccinations_per_million` | daily_vaccinations per 1,000,000 people in the total population of the country |
    | `daily_people_vaccinated` | daily number of people receiving a first COVID-19 vaccine dose (7-day smoothed) |
    | `daily_people_vaccinated_per_hundred` | daily_people_vaccinated per 100 people in the total population of the country |
    """)

    st.subheader("2. WHO Excess Deaths Dataset")
    st.markdown("""
    - **Content:** Estimates of excess mortality for the years 2020 and 2021, broken down by country, age, and sex.
    - Dataset Source: https://www.who.int/data/sets/global-excess-deaths-associated-with-covid-19-modelled-estimates 
    - Rows: 6208
    - Columns: 9
    
    #### Dataset Description

    This dataset, published by the World Health Organization (WHO), provides country-wise estimates of excess deaths associated with the COVID-19 pandemic. It includes detailed demographic breakdowns (by year, sex, and age group) and differentiates between reported and predicted death estimates.

    The purpose of this dataset is to provide a comprehensive understanding of the impact of COVID-19 on global mortality, beyond officially reported COVID-19 deaths.

    #### Column Descriptions

    | Column Name | Description |
    | :------- | :------- |
    | `country` | Country name |			
    | `iso3` | ISO 3166-1 alpha-3 code |				
    | `year` | Year of death |						
    | `sex` | Sex (Female or Male) |						
    | `age_group` | Age-group from 0 to 85 plus |						
    | `type` | Estimate type for select year (reported or predicted) |						
    | `expected` | mean	Expected deaths from all-causes by age, sex and year (mean) |						
    | `acm` | mean	Estimated deaths from all-causes by age, sex and year (mean) |						
    | `excess` | mean*	Excess deaths associated with COVID-19 pandemic from all-causes by age, sex and year (mean) |						

    """)
    
    st.header("Core Data Preparation Logic")
    st.markdown("""
    This is the **most important reasoning** for our core analysis. To compare countries fairly, we must clean and merge these two datasets.

    1.  **Forward-Fill (ffill):** For the vaccination data, missing daily values were filled by carrying the previous day's value forward. This is crucial for cumulative data (like `total_vaccinations`) to avoid incorrectly resetting counts to zero.
    2.  **Population Derivation:** To compare deaths, we must normalize by population. We derived each country's population from the vaccination dataset using the formula: 
        `Population = (daily_vaccinations / daily_vaccinations_per_million) * 1,000,000`
    3.  **Normalization:** We created our key target metric, **`excess_deaths_per_million`**, by dividing the total excess deaths in 2021 by the derived population. This allows us to compare a large country like India to a small one like Andorra fairly.
    """)

def page_eda():
    st.title("Exploratory Data Analysis (EDA)")
    st.markdown("**Reasoning:** To understand the basic distribution and trends in the vaccination data before building complex models.")
    
    st.subheader("Graph 1: Top 10 Countries by Total Vaccinations (Static)")
    st.markdown("This plot shows the sheer scale of vaccination campaigns in the world's most populous countries.")
    
    try:
        st.image("visualization/top_10_total_vaccinations.png", use_container_width=True)
    except Exception:
        st.warning("Could not load `visualization/top_10_total_vaccinations.png`. Please make sure the file exists.")
    
    st.markdown("""
    **Observation:** The vaccination campaigns in **China and India** are on a completely different scale from the rest of the world, dominating the total global count.
    """)
    
    st.subheader("Graph 2: Global Daily Vaccination Trend (Interactive)")
    st.markdown("This plot shows the global \"pace\" of vaccination over time. **You can click and drag to zoom and pan.**")
    
    df = load_vax_cleaned_data()
    
    if df is not None:
        # Aggregate data for the chart
        daily_global_vax = df.groupby('date')['daily_vaccinations'].sum().reset_index()
        
        # Create the interactive Altair chart
        chart = alt.Chart(daily_global_vax).mark_line().encode(
            x=alt.X('date', title='Date'),
            y=alt.Y('daily_vaccinations', title='Daily Vaccinations (in Tens of Millions)'),
            tooltip=[
                alt.Tooltip('date', title='Date'),
                alt.Tooltip('daily_vaccinations', title='Daily Vaccinations', format=',.0f')
            ]
        ).properties(
            title='Global Daily Vaccinations Over Time'
        ).interactive() # This makes the graph interactive!
        
        st.altair_chart(chart, use_container_width=True)
    else:
        st.warning("Could not load `vaccinations_cleaned.csv` to generate interactive chart.")

    st.markdown("""
    **Observation:** The global rollout was not smooth. It occurred in several distinct **waves**, with major peaks in mid-2021 followed by troughs, likely corresponding to vaccine supply, new variants (like Delta and Omicron), and booster campaigns.
    """)

def page_simple_lr():
    st.title("Simple Linear Regression")
    st.markdown("""
    - **Aim:** To predict the number of `people_fully_vaccinated` based on the number of `people_vaccinated` (at least one dose).
    - **Reasoning:** This helps us understand the "conversion rate" from a first dose to a full vaccination.
    """)
    
    st.subheader("Graph: People Vaccinated vs. People Fully Vaccinated")
    try:
        st.image("visualization/simple_lr_scatter.png", use_container_width=True, 
                 caption="Scatter plot showing the relationship between first-dose vaccination and full vaccination.")
    except Exception:
        st.warning("Could not load `visualization/simple_lr_scatter.png`. Please make sure the file exists.")

    st.subheader("Observations")
    st.markdown("""
    - **Result:** The model achieved an **R-squared of 0.98+**, indicating an extremely strong and reliable linear relationship.
    - **Observation:** The plot shows a very tight, straight line. This means that for every 100 people who get one dose, we can confidently predict how many will follow through to full vaccination. This is highly useful for logistics and planning the supply of second doses.
    """)

def page_multi_lr():
    st.title("Multiple Linear Regression")
    st.markdown("""
    - **Aim:** To predict `total_vaccinations` using a combination of all other relevant metrics.
    - **Reasoning:** We used **backward elimination** to find the *most significant* predictors, removing any that were statistically redundant (like `daily_vaccinations_per_million` when `daily_vaccinations` was already present).
    """)
    
    st.subheader("Graph: Actual vs. Predicted Vaccinations")
    try:
        st.image("visualization/multi_lr_scatter.png", use_container_width=True,
                 caption="Scatter plot showing the model's predictions vs. the actual values.")
    except Exception:
        st.warning("Could not load `visualization/multi_lr_scatter.png`. Please make sure the file exists.")
    
    st.subheader("Observations")
    st.markdown("""
    - **Result:** The final model was extremely accurate, explaining over **99% of the variance**.
    - **Observation:** The plot shows the predictions falling on an almost perfect diagonal line. This confirms the high integrity and consistency of the dataset. The most significant predictors for the total vaccination count were, logically, `people_vaccinated`, `people_fully_vaccinated`, and `total_boosters`.
    """)

def page_classification():
    st.title("Classification Models")
    
    st.markdown("""
    - **Aim:** To classify a country as having a **"High" or "Low" vaccination level** (defined as >= 60% fully vaccinated).
    - **Reasoning:** This moves from forecasting a number to predicting an outcome. Can we predict if a country's *strategy* (its pace, booster program, and campaign duration) will lead to success?
    - **Model Used:** Logistic Regression.
    """)
    
    st.subheader("Graph: Model Performance (Confusion Matrix)")
    st.markdown("A confusion matrix shows us where the model was right and where it was wrong.")
    
    try:
        st.image("visualization/classification_confusion_matrix.png", use_container_width=False)
    except Exception:
        st.warning("Could not load `visualization/classification_confusion_matrix.png`. Please make sure the file exists.")

    st.subheader("Observations")
    st.markdown("""
    - **Result:** The model was highly accurate (over 90%).
    - **Observation:** The matrix shows the model was exceptionally good at correctly identifying "High" vaccination countries (True Positives) and "Low" vaccination countries (True Negatives). It made very few mistakes, giving us high confidence in its predictive power.
    """)

def page_neural_network():
    st.title("Neural Network")
    
    st.markdown("""
    - **Aim:** To solve the same classification problem ("High" vs. "Low" vax level) using a more powerful, non-linear model.
    - **Reasoning:** A neural network (specifically, a Multi-layer Perceptron or MLP) can find complex patterns that a linear model like Logistic Regression might miss. For example, it could learn that a "short campaign" is only good if the "daily pace" is *explosively high*.
    """)
    
    st.subheader("Graph: Neural Network Training Loss")
    st.markdown("This plot shows how the neural network \"learned\" over time. The loss (error) decreases as the model improves.")
    
    try:
        st.image("visualization/neural_network_loss_curve.png", use_container_width=True)
    except Exception:
        st.warning("Could not load `visualization/neural_network_loss_curve.png`. Please make sure the file exists.")

    st.subheader("Observations")
    st.markdown("""
    - **Result:** The network achieved excellent accuracy, comparable to the logistic regression model.
    - **Observation:** The loss curve shows the model learned very quickly (loss dropped fast) and then stabilized, which indicates a successful and efficient training process. The fact that its performance was similar to the simpler model suggests that the relationship between the features (pace, duration) and the outcome (success) was relatively linear.
    """)

def page_clustering():
    st.title("Clustering (Discovering Groups)")
    
    st.markdown("""
    - **Aim:** To use **K-Means clustering** to find *natural groupings* of countries based on their vaccination performance, without any preconceived labels.
    - **Reasoning:** This is an unsupervised learning approach. Instead of predicting an outcome, we're asking the machine to "find the pattern" and group similar countries together.
    - **Features Used:** `people_fully_vaccinated_per_hundred`, `total_boosters_per_hundred`, and `daily_vaccinations_per_million`.
    """)
    
    st.subheader("Graph 1: Finding the Optimal Number of Clusters (Elbow Method)")
    st.markdown("""
    We used the "Elbow Method" to find the ideal number of clusters. The "elbow" (the point of diminishing returns) was clearly at **K=3**.
    """)
    
    try:
        st.image("visualization/clustering_elbow_plot.png", use_container_width=True)
    except Exception:
        st.warning("Could not load `visualization/clustering_elbow_plot.png`. Please make sure the file exists.")
    
    st.subheader("Graph 2: The 3 Clusters Visualized")
    try:
        st.image("visualization/clustering_3d_plot.png", use_container_width=True)
    except Exception:
        st.warning("Could not load `visualization/clustering_3d_plot.png`. Please make sure the file exists.")

    st.subheader("Observations: The 3 Clusters")
    st.markdown("""
    The model successfully identified three distinct "types" of countries:

    - **Cluster 0: The "High Achievers"**
      - **Characteristics:** Very high full vaccination and booster coverage, but a low-to-moderate daily pace.
      - **Interpretation:** These are countries (like Western Europe, Canada) that finished their primary campaigns and were in a mature "maintenance" or booster phase.

    - **Cluster 1: The "Active Campaigns"**
      - **Characteristics:** Moderate full vaccination and booster rates, but a very **high daily vaccination pace**.
      - **Interpretation:** These countries were in the middle of their most aggressive rollout, actively working to catch up.
    
    - **Cluster 2: The "Lagging Nations"**
      - **Characteristics:** Low full vaccination, low boosters, and a low daily pace.
      - **Interpretation:** These countries were either just starting their campaigns or had stalled due to supply, logistical, or demand challenges.
    """)

def page_excess_deaths():
    st.title("Core Analysis - Vaccinations vs. Excess Deaths (2021)")
    st.markdown("""
    - **Aim:** To find the statistical relationship between a country's vaccination strategy (its "value" of coverage and "pace" of rollout) and its excess mortality in 2021.
    - **Reasoning:** This is the most important project. It uses the merged and normalized dataset to answer the core question: **Did vaccines work, and what strategy worked best?**
    """)
    
    final_df = load_analysis_data()
    if final_df is None:
        st.error("Failed to load data. Cannot proceed with analysis.")
        return

    st.subheader("Analysis 1: The Overall Relationship")
    st.markdown("This plot shows the foundational relationship between a country's final 2021 vaccination rate and its normalized excess deaths.")
    
    try:
        st.image("visualization/vax_vs_deaths_scatter.png", use_container_width=True)
    except Exception:
        st.warning("Could not load `visualization/vax_vs_deaths_scatter.png`. Please make sure the file exists.")
    
    correlation = final_df['people_fully_vaccinated_per_hundred'].corr(final_df['excess_deaths_per_million'])
    st.markdown(f"**Observation:** The plot shows a clear negative trend. The correlation is **{correlation:.2f}**, which is a **moderate negative relationship**. This confirms that, on average, countries with higher vaccination rates experienced lower excess deaths.")
    
    
    st.subheader("Analysis 2: Identifying Outlier Countries")
    st.markdown("""
    **Reasoning:** Not all countries followed the trend. We ran a regression and analyzed the "residuals" (the error) to find which countries did much better or worse than their vaccination rate would predict.
    """)
    
    # --- Outlier Logic (Runs in the background) ---
    y = final_df['excess_deaths_per_million']
    X_simple = final_df['people_fully_vaccinated_per_hundred']
    X_simple = sm.add_constant(X_simple)
    model = sm.OLS(y, X_simple).fit()
    final_df['residuals'] = model.resid
    
    col1, col2 = st.columns(2)
    with col1:
        st.error("Performed WORSE Than Expected (High Deaths)")
        st.markdown("These countries had *more* deaths than their vax rate predicted:")
        st.dataframe(final_df.nlargest(5, 'residuals')[['country', 'residuals']], use_container_width=True)
        
    with col2:
        st.success("Performed BETTER Than Expected (Low Deaths)")
        st.markdown("These countries had *fewer* deaths than their vax rate predicted:")
        st.dataframe(final_df.nsmallest(5, 'residuals')[['country', 'residuals']], use_container_width=True)

    st.markdown("""
    **Observation:** This is highly insightful.
    - **Worse:** A cluster of Eastern European nations (e.g., Bulgaria, Serbia) had massive excess deaths despite moderate vaccination. This shows other factors (like health system strain or public trust) were critical.
    - **Better:** A cluster of Asia-Pacific nations (e.g., Japan, Australia, New Zealand) had *negative* excess deaths, meaning their public health measures (like border controls and masking) were exceptionally effective.
    """)
    
    
    st.subheader("Analysis 3: What Matters Most? 'Value' (Coverage) vs. 'Pace' (Speed)")
    st.markdown("""
    **Reasoning:** This is the final and most important model. We built a multiple regression to see which specific metric had the biggest impact on reducing excess deaths.
    """)

    st.header("Final Model Results & Conclusion")
    
    # --- Model Logic (Runs in the background) ---
    y_multi = final_df['excess_deaths_per_million']
    X_multi = final_df[['people_fully_vaccinated_per_hundred', 'total_boosters_per_hundred', 'daily_vaccinations_per_million']]
    X_multi = sm.add_constant(X_multi)
    multi_model = sm.OLS(y_multi, X_multi).fit()
    
    # Get coefficients
    coef_full_vax = multi_model.params['people_fully_vaccinated_per_hundred']
    p_full_vax = multi_model.pvalues['people_fully_vaccinated_per_hundred']
    
    coef_boosters = multi_model.params['total_boosters_per_hundred']
    p_boosters = multi_model.pvalues['total_boosters_per_hundred']
    
    coef_daily = multi_model.params['daily_vaccinations_per_million']
    p_daily = multi_model.pvalues['daily_vaccinations_per_million']
    
    col1, col2 = st.columns(2)
    with col1:
        st.success("Finding 1: 'Value' (Coverage) is CRITICAL")
        st.metric(label="Impact of 1% Full Vaccination", value=f"{coef_full_vax:.2f} deaths / million", delta=f"p-value: {p_full_vax:.3f} (Significant)")
        st.metric(label="Impact of 1% Booster Coverage", value=f"{coef_boosters:.2f} deaths / million", delta=f"p-value: {p_boosters:.3f} (Significant)")
        
    with col2:
        st.warning("Finding 2: 'Pace' (Speed) is Less Significant")
        st.metric(label="Impact of Daily Vax Pace", value=f"{coef_daily:.2f} deaths / million", delta=f"p-value: {p_daily:.3f} (Not Significant)")
        st.markdown(f"""
        The p-value for **'Pace' was {p_daily:.3f}, which is not significant**. This doesn't mean speed was useless! It means its effect is *already captured* by the total coverage. A high pace just meant a country achieved a high "value" *sooner*.
        """)
        
    st.header("Final Conclusion")
    st.markdown(f"""
    To drastically reduce excess death numbers, the data from 2021 shows that the most effective strategy is achieving the highest possible **\"value\"** of vaccination coverage.

    Specifically, **boosters had the strongest life-saving effect**, reducing the death toll by an estimated **{coef_boosters:.0f} deaths per million** for every 1% of the population that received one. Achieving a high rate of *full vaccination* was also critical, saving an estimated **{coef_full_vax:.0f} deaths per million** for every 1% of coverage.

    The "pace" of vaccination was the *means* to this end, but the final **coverage** was the metric most strongly correlated with saving lives over the full year.
    """)

# ---------------------------------------------------------------------
# Main App Navigation
# ---------------------------------------------------------------------
def main():
    st.sidebar.title("Project Navigator")
    
    # Define the pages
    pages = {
        "Introduction & Data": page_intro,
        "1. Exploratory Data Analysis": page_eda,
        "2. Simple Linear Regression": page_simple_lr,
        "3. Multiple Linear Regression": page_multi_lr,
        "4. Classification (Logistic)": page_classification,
        "5. Neural Network": page_neural_network,
        "6. Clustering (K-Means)": page_clustering,
        "7. Core Analysis: Vax vs. Deaths": page_excess_deaths,
    }
    
    # Create the radio button navigation
    page_selection = st.sidebar.radio("Go to Project:", list(pages.keys()))
    
    # Call the selected page function
    page = pages[page_selection]
    page()

if __name__ == "__main__":
    main()