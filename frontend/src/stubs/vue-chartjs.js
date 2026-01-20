import { h } from 'vue';

const DummyChart = {
    name: 'DummyChart',
    props: ['chartData', 'options', 'height', 'width'],
    render() {
        return h('div', {
            style: {
                color: 'gray',
                padding: '10px',
                border: '1px dashed gray',
                height: this.height ? this.height + 'px' : '200px',
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
            }
        }, 'Chart Placeholder');
    }
};

export const Bar = DummyChart;
export const Line = DummyChart;
export const mixins = { reactiveProp: {} };
