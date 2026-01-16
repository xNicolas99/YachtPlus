<template>
  <div class="chart-container">
    <Line :data="chartData" :options="mergedOptions" />
  </div>
</template>

<script>
import { Line } from 'vue-chartjs'
import { Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend } from 'chart.js'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend)

export default {
  name: 'PercentLineChart',
  components: { Line },
  props: {
    chartData: {
      type: Object,
      required: true
    },
    chartOptions: {
      type: Object,
      default: () => ({})
    }
  },
  computed: {
    mergedOptions() {
      // Default options for 0-100% scaling
      const defaultOptions = {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            min: 0,
            max: 100,
            ticks: {
              stepSize: 10
            }
          },
          x: {
            type: 'category', // Ensure x-axis is treated as category (or time if configured)
            display: false // Often hidden in these mini-charts
          }
        },
        plugins: {
          legend: {
            display: false
          }
        }
      };

      return { ...defaultOptions, ...this.chartOptions };
    }
  }
}
</script>

<style scoped>
.chart-container {
  position: relative;
  height: 200px;
}
</style>
