<!-- Chart.js CDN -->
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<script>
document.addEventListener("DOMContentLoaded", function () {
    // -------------------------------------------------------------
    // 1. Primary Monthly Revenue Line Chart
    // -------------------------------------------------------------
    const salesCanvas = document.getElementById('salesChart');
    if (salesCanvas) {
        const salesCtx = salesCanvas.getContext('2d');
        
        // Data injected directly from Flask render_template
        const chartLabels = {{ chart_labels | tojson }};
        const chartData = {{ chart_data | tojson }};

        new Chart(salesCtx, {
            type: 'line',
            data: {
                labels: chartLabels,
                datasets: [{
                    label: 'Monthly Revenue (₹)',
                    data: chartData,
                    borderColor: '#111827',
                    backgroundColor: 'rgba(17, 24, 39, 0.08)',
                    borderWidth: 2.5,
                    fill: true,
                    tension: 0.35,
                    pointRadius: 4,
                    pointBackgroundColor: '#111827'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return ' ₹' + context.parsed.y.toLocaleString('en-IN');
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {
                                return '₹' + value.toLocaleString('en-IN');
                            }
                        },
                        grid: { color: 'rgba(0, 0, 0, 0.05)' }
                    },
                    x: {
                        grid: { display: false }
                    }
                }
            }
        });
    }

    // -------------------------------------------------------------
    // 2. Fetch Deep Analytics (/admin/api/analytics)
    // -------------------------------------------------------------
    fetch('/admin/api/analytics')
        .then(response => {
            if (!response.ok) throw new Error("Unauthorized or server error");
            return response.json();
        })
        .then(data => {
            // Render Category Pie/Doughnut Chart (if container exists)
            const catCanvas = document.getElementById('categoryChart');
            if (catCanvas && data.categories && data.categories.length > 0) {
                new Chart(catCanvas.getContext('2d'), {
                    type: 'doughnut',
                    data: {
                        labels: data.categories,
                        datasets: [{
                            data: data.category_sales,
                            backgroundColor: [
                                '#111827', '#4b5563', '#9ca3af', 
                                '#d1d5db', '#3b82f6', '#10b981'
                            ]
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { position: 'bottom' }
                        }
                    }
                });
            }

            // Render Top Products Bar Chart (if container exists)
            const topCanvas = document.getElementById('topProductsChart');
            if (topCanvas && data.top_product_names && data.top_product_names.length > 0) {
                new Chart(topCanvas.getContext('2d'), {
                    type: 'bar',
                    data: {
                        labels: data.top_product_names,
                        datasets: [{
                            label: 'Units Sold',
                            data: data.top_product_units,
                            backgroundColor: '#111827',
                            borderRadius: 6
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        indexAxis: 'y',
                        plugins: { legend: { display: false } },
                        scales: {
                            x: { beginAtZero: true, grid: { color: 'rgba(0,0,0,0.05)' } },
                            y: { grid: { display: false } }
                        }
                    }
                });
            }
        })
        .catch(err => console.log('Analytics endpoint check:', err));
});
</script>