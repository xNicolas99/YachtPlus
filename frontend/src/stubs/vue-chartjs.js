// Stub for vue-chartjs
export const Line = {
  name: 'LineChart',
  render() { return null }
}
export const Bar = {
  name: 'BarChart',
  render() { return null }
}
export const mixins = {
  reactiveProp: {
    props: {
      chartData: {
        type: Object,
        default: null
      }
    }
  }
}
